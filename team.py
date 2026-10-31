"""Wires the four agents into one AutoGen team: Query -> Knowledge -> Resolution -> Log.

Run one complaint from the command line:
    python team.py "I forgot my password and can't log in."
"""

import asyncio
import re
import sys
from dataclasses import dataclass, field
from typing import AsyncGenerator

from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import BaseChatMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from agents.knowledge_agent import create_knowledge_agent
from agents.log_agent import create_log_agent
from agents.model_client import get_model_client
from agents.query_agent import create_query_agent
from agents.resolution_agent import create_resolution_agent

AGENT_LABELS = {
    "query_agent": "Customer Query Agent",
    "knowledge_agent": "Knowledge Base Agent",
    "resolution_agent": "Resolution Agent",
    "log_agent": "Log Agent",
}


@dataclass
class TicketOutcome:
    """Everything the UI needs once a ticket has gone through the team."""

    steps: list[tuple[str, str]] = field(default_factory=list)
    category: str = ""
    urgency: str = ""
    sentiment: str = ""
    summary: str = ""
    reply: str = ""
    used_sources: str = ""
    confidence: str = ""
    ticket_id: str = ""
    status: str = ""
    escalation_reason: str = ""


def build_team(model_client=None) -> RoundRobinGroupChat:
    model_client = model_client or get_model_client()
    agents = [
        create_query_agent(model_client),
        create_knowledge_agent(model_client),
        create_resolution_agent(model_client),
        create_log_agent(model_client),
    ]
    # Stop as soon as the Log Agent reports LOGGED; the message cap is a safety net.
    termination = TextMentionTermination("LOGGED", sources=["log_agent"]) | MaxMessageTermination(8)
    return RoundRobinGroupChat(agents, termination_condition=termination)


def build_task(complaint: str, customer_name: str = "", order_id: str = "") -> str:
    return (
        "New customer support ticket.\n"
        f"Customer name: {customer_name.strip() or 'not given'}\n"
        f"Order ID: {order_id.strip() or 'not given'}\n"
        f"Complaint: {complaint.strip()}"
    )


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _update_outcome(outcome: TicketOutcome, source: str, content: str) -> None:
    if source == "query_agent":
        outcome.category = _field(content, "CATEGORY")
        outcome.urgency = _field(content, "URGENCY")
        outcome.sentiment = _field(content, "SENTIMENT")
        outcome.summary = _field(content, "SUMMARY")
    elif source == "resolution_agent":
        reply = re.search(r"REPLY:\s*(.*?)\s*(?:^USED_SOURCES:|^CONFIDENCE:|\Z)", content, re.DOTALL | re.MULTILINE)
        outcome.reply = reply.group(1).strip() if reply else content.strip()
        outcome.used_sources = _field(content, "USED_SOURCES")
        outcome.confidence = _field(content, "CONFIDENCE")
    elif source == "log_agent" and "LOGGED" in content:
        match = re.search(r"LOGGED (\S+) \| status: (\w+)(?: \| reason: (.+))?", content)
        if match:
            outcome.ticket_id, outcome.status = match.group(1), match.group(2)
            outcome.escalation_reason = (match.group(3) or "").strip()


async def run_ticket(
    complaint: str, customer_name: str = "", order_id: str = "", team: RoundRobinGroupChat | None = None
) -> AsyncGenerator[tuple[str, str] | TicketOutcome, None]:
    """Yield (agent_name, output) as each agent finishes, then the final TicketOutcome."""
    team = team or build_team()
    outcome = TicketOutcome()
    task = build_task(complaint, customer_name, order_id)

    async for item in team.run_stream(task=task, output_task_messages=False):
        if isinstance(item, TaskResult):
            continue  # the final summary; let the stream finish so the team can be reused
        if isinstance(item, BaseChatMessage) and item.source in AGENT_LABELS:
            content = item.to_text()
            outcome.steps.append((item.source, content))
            _update_outcome(outcome, item.source, content)
            yield item.source, content
    yield outcome


async def _main(complaint: str) -> None:
    async for item in run_ticket(complaint):
        if isinstance(item, TicketOutcome):
            print(f"\n=== {item.ticket_id}: {item.status} {('(' + item.escalation_reason + ')') if item.escalation_reason else ''}")
        else:
            source, content = item
            print(f"\n--- {AGENT_LABELS[source]} ---\n{content}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # the policies use the rupee sign; Windows consoles default to cp1252
    if len(sys.argv) < 2:
        sys.exit('Usage: python team.py "your complaint"')
    asyncio.run(_main(" ".join(sys.argv[1:])))
