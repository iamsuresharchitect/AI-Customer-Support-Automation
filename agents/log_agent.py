"""Log Agent: applies the escalation rule and records every ticket with the log_ticket tool."""

import csv
import re
from datetime import datetime
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "logs" / "tickets.csv"

COLUMNS = [
    "ticket_id",
    "timestamp",
    "customer_name",
    "order_id",
    "complaint",
    "category",
    "urgency",
    "sentiment",
    "language",
    "summary",
    "kb_sources",
    "response",
    "confidence",
    "status",
    "escalation_reason",
    # Human review of escalated tickets (see agents/review_agent.py)
    "review_status",
    "reviewer",
    "final_response",
    "reviewed_at",
]

PENDING = "Pending approval"

# Legal threats, fraud and payment disputes always go to a human.
SENSITIVE_PATTERNS = {
    "legal threat": r"\b(lawyer|legal|sue|suing|court|consumer forum|police)\b",
    "possible fraud": r"\b(fraud|scam|hacked|unauthori[sz]ed|stolen)\b",
    "payment dispute": r"\b(chargeback|dispute|charged (me )?(twice|three times|\d+ times|again)|double charged|contacting my bank|call my bank)\b",
}


def decide_escalation(complaint: str, urgency: str, sentiment: str, kb_sources: str, confidence: str) -> list[str]:
    """Return the reasons to escalate; an empty list means the ticket is resolved."""
    reasons = []
    if urgency.strip().lower() == "high":
        reasons.append("High urgency")
    if sentiment.strip().lower() in {"angry", "very angry"}:
        reasons.append(f"{sentiment.strip()} customer")
    if not kb_sources.strip() or kb_sources.strip().upper() == "NONE":
        reasons.append("No matching document")
    if confidence.strip().lower() == "low":
        reasons.append("Low confidence")
    text = complaint.lower()
    for label, pattern in SENSITIVE_PATTERNS.items():
        if re.search(pattern, text):
            reasons.append(label.capitalize())
    return reasons


def _read_rows() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(rows: list[dict]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col) or "" for col in COLUMNS})


def _upgrade_log() -> None:
    """Rewrite a log made by an older version so it has every current column."""
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if header == COLUMNS:
        return
    rows = _read_rows()
    for row in rows:
        row["language"] = row.get("language") or "English"  # older versions only handled English
        if not row.get("review_status"):
            row["review_status"] = PENDING if row.get("status") == "Escalated" else "Not needed"
        if row["review_status"] == "Not needed" and not row.get("final_response"):
            row["final_response"] = row.get("response", "")
    _write_rows(rows)


def _next_ticket_id() -> str:
    return f"TKT-{len(_read_rows()) + 1:04d}"


def get_ticket(ticket_id: str) -> dict | None:
    _upgrade_log()
    return next((row for row in _read_rows() if row["ticket_id"] == ticket_id), None)


def update_ticket(ticket_id: str, **fields: str) -> bool:
    """Change fields of one logged ticket; returns False if the ticket is not in the log."""
    _upgrade_log()
    rows = _read_rows()
    for row in rows:
        if row["ticket_id"] == ticket_id:
            row.update(fields)
            _write_rows(rows)
            return True
    return False


def log_ticket(
    customer_name: str,
    order_id: str,
    complaint: str,
    category: str,
    urgency: str,
    sentiment: str,
    summary: str,
    kb_sources: str,
    response: str,
    confidence: str,
    language: str = "English",
    extra_escalation_reason: str = "",
) -> str:
    """Append one ticket to logs/tickets.csv, apply the escalation rule, and return the ticket ID and status. Pass extra_escalation_reason only if the case needs a human for a reason the rule may miss."""
    reasons = decide_escalation(complaint, urgency, sentiment, kb_sources, confidence)
    if extra_escalation_reason.strip():
        reasons.append(extra_escalation_reason.strip())
    status = "Escalated" if reasons else "Resolved"

    _upgrade_log()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_FILE.exists()
    ticket_id = _next_ticket_id()
    row = {
        "ticket_id": ticket_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_name": customer_name.strip(),
        "order_id": order_id.strip(),
        "complaint": complaint.strip(),
        "category": category.strip(),
        "urgency": urgency.strip(),
        "sentiment": sentiment.strip(),
        "language": language.strip() or "English",
        "summary": summary.strip(),
        "kb_sources": kb_sources.strip() or "NONE",
        "response": response.strip(),
        "confidence": confidence.strip(),
        "status": status,
        "escalation_reason": " + ".join(reasons),
        # Escalated replies wait for a support person; resolved ones go out as written.
        "review_status": PENDING if reasons else "Not needed",
        "reviewer": "",
        "final_response": "" if reasons else response.strip(),
        "reviewed_at": "",
    }
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)

    reason_text = f" | reason: {row['escalation_reason']}" if reasons else ""
    return f"LOGGED {ticket_id} | status: {status}{reason_text}"


SYSTEM_MESSAGE = """You are the Log Agent for ShopNest customer support.
Your only job is to record the ticket by calling the log_ticket tool exactly once.

Fill the arguments from the conversation:
- customer_name, order_id, complaint: from the original ticket (use "" if not given). Copy the complaint exactly.
- category, urgency, sentiment, language, summary: from the Query Agent.
- kb_sources: the Resolution Agent's USED_SOURCES line (NONE if it says NONE).
- response: the Resolution Agent's REPLY text, copied exactly.
- confidence: the Resolution Agent's CONFIDENCE.
- extra_escalation_reason: leave empty in almost every case. The rule already covers urgency, anger, missing documents, low confidence, legal threats, fraud and payment disputes. Only fill it (in under 8 words) for a different reason a human is needed, such as a safety risk.

The tool applies the escalation rule. Do not write anything else."""


def create_log_agent(model_client) -> AssistantAgent:
    return AssistantAgent(
        name="log_agent",
        description="Records every ticket to the log file and escalates complicated cases to human support. Speaks last, once the Resolution Agent has written the reply.",
        model_client=model_client,
        system_message=SYSTEM_MESSAGE,
        tools=[log_ticket],
        reflect_on_tool_use=False,
        tool_call_summary_format="{result}",
    )
