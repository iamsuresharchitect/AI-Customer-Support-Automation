"""Human-in-the-loop review: a support person approves, edits or rejects an escalated reply
before it goes to the customer.

AutoGen's UserProxyAgent stands in for the support person. In the Streamlit app its input
comes from the Approvals tab; on the command line it asks in the terminal.
"""

from datetime import datetime

from autogen_agentchat.agents import UserProxyAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from agents.log_agent import PENDING, update_ticket


def review_request(ticket: dict) -> str:
    """The message the reviewer sees: why the ticket was escalated and the draft reply."""
    return (
        f"Escalated ticket {ticket['ticket_id']} needs a human decision.\n"
        f"Reason: {ticket.get('escalation_reason') or '-'}\n"
        f"Complaint: {ticket.get('complaint', '')}\n\n"
        f"Draft reply:\n{ticket.get('response', '')}\n\n"
        "Type APPROVE to send the draft, EDIT followed by your own reply to send that instead, "
        "or REJECT followed by a note to stop the reply."
    )


def parse_decision(decision: str, draft: str) -> tuple[str, str]:
    """Turn the reviewer's answer into (review_status, final_response)."""
    text = decision.strip()
    command = text.split(maxsplit=1)[0].upper().rstrip(":") if text else ""
    rest = text[len(command):].lstrip(" :\n") if command in {"APPROVE", "EDIT", "REJECT"} else text
    if command == "APPROVE":
        return "Approved", draft
    if command == "REJECT":
        return (f"Rejected: {rest}" if rest else "Rejected"), ""
    if rest:  # EDIT <reply>, or a reply typed without the keyword
        return "Edited", rest
    return PENDING, ""


async def review_ticket(ticket: dict, input_func=None, reviewer: str = "Support team") -> str:
    """Ask the reviewer through a UserProxyAgent and save the decision; returns the review status.

    input_func is the UserProxyAgent's input function. None means the terminal's input().
    """
    proxy = UserProxyAgent(
        "support_reviewer",
        description="A human support person who approves, edits or rejects escalated replies.",
        input_func=input_func,
    )
    request = TextMessage(content=review_request(ticket), source="log_agent")
    response = await proxy.on_messages([request], CancellationToken())
    status, final_response = parse_decision(response.chat_message.to_text(), ticket.get("response", ""))
    if status != PENDING:
        update_ticket(
            ticket["ticket_id"],
            review_status=status,
            reviewer=reviewer.strip() or "Support team",
            final_response=final_response,
            reviewed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    return status
