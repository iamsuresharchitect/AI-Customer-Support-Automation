"""Pieces shared by the customer portal and the admin panel."""

import html
import re

import pandas as pd
import streamlit as st

from agents.followup import rewrite_followup
from agents.log_agent import COLUMNS, LOG_FILE, PENDING, update_ticket
from orders import get_order, order_summary
from team import AGENT_LABELS, TicketOutcome, run_ticket

AGENT_STEPS = ["query_agent", "knowledge_agent", "resolution_agent", "log_agent"]
AGENT_ROLES = {
    "query_agent": "Reads the complaint: category, urgency, mood, language",
    "knowledge_agent": "Searches company policies in ChromaDB",
    "resolution_agent": "Writes a reply from those policies, in the customer's language",
    "log_agent": "Records the ticket and applies the escalation rule",
}

def load_log() -> pd.DataFrame:
    if not LOG_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(LOG_FILE, dtype=str).fillna("")
    return df.reindex(columns=COLUMNS, fill_value="")  # logs from older versions lack the newer columns


def as_paragraphs(text: str) -> str:
    """Turn plain reply text into HTML paragraphs without the large gaps of pre-wrap."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    def fmt(block: str) -> str:
        safe = html.escape(block).replace(chr(10), "<br>")
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)  # Claude sometimes uses **bold**

    return "".join(f"<p>{fmt(b)}</p>" for b in blocks)


AGENT_ICONS = {"query_agent": "🧠", "knowledge_agent": "📚", "resolution_agent": "✍️", "log_agent": "🛡️"}


def step_card(number: int, source: str, content: str) -> str:
    return (
        f'<div class="step"><div class="dot">{AGENT_ICONS[source]}</div><div class="body">'
        f'<div class="head"><div class="name">{number}. {AGENT_LABELS[source]}</div><div class="done">● Done</div></div>'
        f'<div class="role">{AGENT_ROLES[source]}</div>'
        # <br> instead of raw newlines: a blank line would end the HTML block in Markdown.
        f'<div class="out">{html.escape(content.strip()).replace(chr(10), "<br>")}</div></div></div>'
    )


async def process_ticket(
    complaint: str, name: str, order_id: str, on_step, order_details: str = "", customer_id: str = ""
) -> TicketOutcome | None:
    """Run the agent team; on_step(number, source, content) is called as each agent finishes."""
    outcome = None
    step = 0
    async for item in run_ticket(complaint, name, order_id, order_details=order_details):
        if isinstance(item, TicketOutcome):
            outcome = item
            continue
        source, content = item
        step += 1  # numbered in the order the selector picked them
        on_step(step, source, content)
    if outcome and outcome.ticket_id and customer_id:
        # The portal knows who the customer is and which order they picked, so record that exactly.
        update_ticket(outcome.ticket_id, customer_id=customer_id, **({"order_id": order_id} if order_id else {}))
    return outcome


async def process_followup(parent, followup: str, name: str, customer_id: str, on_step) -> tuple[str, TicketOutcome | None]:
    """Rewrite a follow-up on an earlier ticket into a standalone request, then run the agents on it."""
    _, _, previous_reply = customer_status(parent)
    standalone = await rewrite_followup(parent["complaint"], previous_reply, followup)
    order = get_order(parent["order_id"]) if parent["order_id"] else None
    outcome = await process_ticket(
        standalone, name, parent["order_id"], on_step, order_details=order_summary(order) if order else "", customer_id=customer_id
    )
    if outcome and outcome.ticket_id:
        update_ticket(outcome.ticket_id, parent_ticket=parent["ticket_id"], followup_text=followup.strip())
    return standalone, outcome


def customer_status(row) -> tuple[str, str, str]:
    """What the customer sees for a ticket: (label, css class, reply text)."""
    review = row["review_status"]
    if row["status"] == "Resolved":
        return "Answered", "ts-answered", row["final_response"] or row["response"]
    if review == PENDING:
        return "Under review", "ts-review", ""
    if review.startswith("Rejected"):
        return "Closed", "ts-closed", ""
    return "Answered", "ts-answered", row["final_response"] or row["response"]


def result_card(outcome: TicketOutcome) -> str:
    escalated = outcome.status == "Escalated"
    badge = (
        '<span class="badge badge-escalated">⚠ Escalated</span>'
        if escalated
        else '<span class="badge badge-resolved">✓ Resolved</span>'
    )
    reason = f'<div class="reason">{html.escape(outcome.escalation_reason)}</div>' if outcome.escalation_reason else ""
    handoff = (
        '<div class="handoff">Handed to human support. A support person must approve this reply in the Approvals tab before it is sent.</div>'
        if escalated
        else ""
    )
    return (
        f'<div class="card">{badge}{reason}'
        f'<div class="meta"><span><b>Ticket</b> {html.escape(outcome.ticket_id)}</span>'
        f"<span><b>Category</b> {html.escape(outcome.category or '-')}</span>"
        f"<span><b>Urgency</b> {html.escape(outcome.urgency or '-')}</span>"
        f"<span><b>Sentiment</b> {html.escape(outcome.sentiment or '-')}</span>"
        f"<span><b>Language</b> {html.escape(outcome.language or '-')}</span></div>"
        f'<div class="reply">{as_paragraphs(outcome.reply)}</div>'
        f"<div class=\"foot\">Sources: {html.escape(outcome.used_sources or 'NONE')} &nbsp;·&nbsp; "
        f"Confidence: {html.escape(outcome.confidence or '-')}</div>{handoff}</div>"
    )




def logout_button(user: dict) -> None:
    st.markdown(
        f'<div class="hello">Signed in as<b>{html.escape(user["name"])} · {html.escape(user["username"])}</b></div>',
        unsafe_allow_html=True,
    )
    if st.button("Log out", key="logout"):
        for key in list(st.session_state):
            del st.session_state[key]
        st.rerun()


PIPELINE_NAMES = {"query_agent": "Query Agent", "knowledge_agent": "Knowledge Agent", "resolution_agent": "Resolution Agent", "log_agent": "Log Agent"}
PIPELINE_PACKETS = ["category + mood", "policy passages", "reply + confidence"]  # what flows between agents


def pipeline_html(done: set, active: str | None = None, headline: str = "", finished: bool = False) -> str:
    """Animated infographic of the four AutoGen agents: the active agent pulses, packets travel along the links."""
    parts = []
    for i, agent in enumerate(AGENT_STEPS):
        state = "done" if agent in done else "active" if agent == active else "wait"
        label = {"done": "Done", "active": "Working...", "wait": "Waiting"}[state]
        parts.append(
            f'<div class="pl-node {state}"><div class="orb">{AGENT_ICONS[agent]}</div>'
            f'<div class="name">{PIPELINE_NAMES[agent]}</div><div class="state">{label}</div></div>'
        )
        if i < len(AGENT_STEPS) - 1:
            nxt = AGENT_STEPS[i + 1]
            link = "done" if nxt in done else "flowing" if agent in done and nxt == active else ""
            if finished:
                link = "done flowing"
            parts.append(
                f'<div class="pl-linkwrap"><div class="pl-link {link}" style="--d:{i * 0.35:.2f}s"></div>'
                f'<div class="pl-tag">{PIPELINE_PACKETS[i]}</div></div>'
            )
    head = headline or ("All agents finished" if finished else "AutoGen SelectorGroupChat is routing your request")
    return (
        f'<div class="pl-box{" finished" if finished else ""}"><div class="pl-head"><span class="dot"></span>{html.escape(head)}</div>'
        f'<div class="pl-row">{"".join(parts)}</div></div>'
    )
