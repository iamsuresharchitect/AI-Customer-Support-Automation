"""ShopNest AI Support Desk - Streamlit UI.

    streamlit run app.py
"""

import asyncio
import html
import io
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agents.knowledge_agent import KB_DIR
from agents.log_agent import COLUMNS, LOG_FILE, PENDING
from agents.review_agent import review_ticket
from team import AGENT_LABELS, TicketOutcome, run_ticket

st.set_page_config(page_title="ShopNest AI Support Desk", page_icon="✦", layout="wide")

SAMPLE_COMPLAINTS = {
    "Write my own": ("", "", ""),
    "Late order": ("Where is my order? It was supposed to arrive yesterday.", "Priya", "ORD-4512"),
    "Return shoes": ("I want to return the shoes I bought last week. How do I get a refund?", "Arjun", "ORD-4630"),
    "Forgot password": ("I forgot my password and can't log in.", "Meena", ""),
    "Broken blender": ("The blender I received is broken. Can I get a replacement?", "Karthik", "ORD-4701"),
    "Charged three times": (
        "You charged my card three times! Fix this now or I'm contacting my bank and a lawyer.",
        "Rahul",
        "ORD-4719",
    ),
    "Corporate gift cards": ("Do you sell gift cards for a company of 500 employees with custom branding?", "Anita", ""),
    "Return shoes (Tamil)": ("நான் கடந்த வாரம் வாங்கிய காலணிகளைத் திருப்பி அனுப்ப வேண்டும். பணத்தை எப்படித் திரும்பப் பெறுவது?", "Arjun", "ORD-4630"),
    "Late order (Malayalam)": ("എന്റെ ഓർഡർ ഇതുവരെ എത്തിയിട്ടില്ല. ഇന്നലെ എത്തേണ്ടതായിരുന്നു.", "Anu", "ORD-4655"),
    "Forgot password (Telugu)": ("నేను నా పాస్‌వర్డ్ మర్చిపోయాను, లాగిన్ అవ్వలేకపోతున్నాను.", "Ravi", ""),
    "Late order (Hindi)": ("मेरा ऑर्डर अभी तक नहीं आया। यह कल आना था।", "Priya", "ORD-4512"),
}

AGENT_STEPS = ["query_agent", "knowledge_agent", "resolution_agent", "log_agent"]
AGENT_ROLES = {
    "query_agent": "Reads the complaint: category, urgency, mood, language",
    "knowledge_agent": "Searches company policies in ChromaDB",
    "resolution_agent": "Writes a reply from those policies, in the customer's language",
    "log_agent": "Records the ticket and applies the escalation rule",
}

# Chart colors from the validated reference palette (light mode). Blue for single-series charts,
# a one-hue blue ramp for ordered levels, and the fixed status colors (always labelled).
INK = "#0F1B3D"
MUTED = "#5B6B8C"
GRID = "#E3EAF8"
BLUE = "#2a78d6"
VIOLET = "#6250d6"
URGENCY_COLORS = {"Low": "#86b6ef", "Medium": "#2a78d6", "High": "#104281"}
SENTIMENT_COLORS = {"Positive": "#cde2fb", "Neutral": "#9ec5f4", "Frustrated": "#5598e7", "Angry": "#256abf", "Very Angry": "#104281"}
STATUS_COLORS = {"Resolved": "#0ca30c", "Escalated": "#d03b3b"}


def rate_color(rate: float) -> str:
    """Deeper blue for categories the AI handles well, lighter where humans step in more."""
    return "#104281" if rate >= 0.75 else "#2a78d6" if rate >= 0.4 else "#86b6ef"

STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #F5F8FF; --panel: #FFFFFF; --line: #DCE6FA; --line-strong: #A9C4F5; --ink: #0F1B3D; --muted: #5B6B8C;
  --blue: #2563EB; --cyan: #0EA5E9; --violet: #7C3AED; --glow: 0 10px 30px -12px rgba(37,99,235,0.35);
  --good: #0b7f0b; --good-bg: #E8F6EA; --bad: #B42E2E; --bad-bg: #FCECEC;
}
html, body, [class*="css"], .stMarkdown, .stTextInput, .stTextArea, .stSelectbox, button {font-family: 'Inter', sans-serif;}
.stApp {background: radial-gradient(1100px 520px at 75% -12%, rgba(59,130,246,0.14), transparent 60%),
  radial-gradient(800px 480px at -10% 35%, rgba(124,58,237,0.08), transparent 60%), #F5F8FF;}
.block-container {padding-top: 2rem; max-width: 1280px;}
h1, h2, h3, .display {font-family: 'Space Grotesk', sans-serif !important;}
[data-testid="stHeader"] {background: transparent;}
/* Sidebar */
[data-testid="stSidebar"] {background: #FFFFFF; border-right: 1px solid var(--line);}
.side-brand {display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.3rem;}
.side-brand .logo {width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(135deg, #2563EB, #7C3AED);
  display: flex; align-items: center; justify-content: center; box-shadow: var(--glow); font-size: 1.2rem; color: #fff;}
.side-brand .name {font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.15rem; color: var(--ink); line-height: 1.15;}
.side-brand .name small {display: block; font-family: 'Inter', sans-serif; font-weight: 500; font-size: 0.75rem; color: var(--blue);}
.side-status {display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--good); margin: 0.6rem 0 0.4rem;}
.side-status:before {content: ""; width: 7px; height: 7px; border-radius: 50%; background: #16a34a; box-shadow: 0 0 8px #16a34a;}
.side-label {font-size: 0.7rem; letter-spacing: 1.8px; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 1.3rem 0 0.6rem;}
.side-agent {display: flex; gap: 0.7rem; align-items: flex-start; padding: 0.6rem 0.7rem; border: 1px solid var(--line); border-radius: 12px;
  background: #F8FAFF; margin-bottom: 0.5rem;}
.side-agent .num {flex: 0 0 26px; height: 26px; border-radius: 8px; background: #E4EDFF; color: var(--blue);
  display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 600;}
.side-agent .txt b {display: block; color: var(--ink); font-size: 0.85rem; font-weight: 600;}
.side-agent .txt small {color: var(--muted); font-size: 0.75rem; line-height: 1.35;}
[data-testid="stSidebar"] [data-testid="stExpander"] {background: #F8FAFF; border: 1px solid var(--line); border-radius: 12px;}
/* Hero: a deep-blue feature panel so the AI brain glows */
.hero {position: relative; border-radius: 24px; padding: 2rem 2.2rem 1.4rem; margin-bottom: 1.6rem;
  background: radial-gradient(700px 300px at 50% 60%, rgba(59,130,246,0.35), transparent 70%), linear-gradient(160deg, #0E1E48, #081233);
  box-shadow: 0 30px 70px -35px rgba(37,99,235,0.65); overflow: hidden;}
.hero .eyebrow {font-size: 0.72rem; letter-spacing: 2.6px; text-transform: uppercase; color: #7DD3FC; font-weight: 600;}
.hero h1 {font-size: 2.7rem; font-weight: 700; color: #fff; margin: 0.35rem 0 0.4rem; padding: 0; line-height: 1.1;}
.hero h1 .grad {background: linear-gradient(90deg, #38BDF8, #60A5FA 45%, #A78BFA); -webkit-background-clip: text; background-clip: text; color: transparent;}
.hero p {color: #A9BAD9; font-size: 1rem; max-width: 640px; margin: 0;}
.hero svg {width: 100%; height: auto; margin-top: 1rem; display: block;}
.flow {stroke-dasharray: 6 8; animation: flow 1.6s linear infinite;}
@keyframes flow {to {stroke-dashoffset: -28;}}
.orb-ring {transform-origin: 500px 165px; animation: pulse 3s ease-in-out infinite;}
@keyframes pulse {0%,100% {opacity: 0.35; transform: scale(1);} 50% {opacity: 0.8; transform: scale(1.06);}}
.hero .secure {display: flex; justify-content: center; margin-top: 0.4rem;}
.hero .secure span {border: 1px solid rgba(125,180,255,0.3); background: rgba(8,18,46,0.7); color: #A9BAD9; border-radius: 999px; padding: 0.35rem 1rem; font-size: 0.78rem;}
/* Tabs */
[role="tablist"] {gap: 0.35rem; background: #FFFFFF; border: 1px solid var(--line) !important; padding: 0.35rem; border-radius: 14px; width: fit-content; box-shadow: var(--glow);}
[role="tablist"] [role="tab"] {border-radius: 10px !important; padding: 0.45rem 1.3rem !important; border: none !important;}
[role="tablist"] [role="tab"] p {font-weight: 500; font-size: 0.92rem; color: var(--muted);}
[role="tablist"] [role="tab"][aria-selected="true"] {background: linear-gradient(135deg, #2563EB, #4F46E5) !important;}
[role="tablist"] [role="tab"][aria-selected="true"] p {color: #fff !important;}
/* Panels and inputs */
[data-testid="stForm"], .card {background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 1.4rem 1.5rem; box-shadow: var(--glow);}
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {border-radius: 12px !important; background: #F8FAFF !important; border-color: var(--line) !important;}
.stButton button, .stDownloadButton button {border-radius: 12px; border: 1px solid var(--line-strong); background: #FFFFFF; color: var(--blue); font-weight: 600;}
[data-testid="stFormSubmitButton"] button {border-radius: 12px; padding: 0.55rem 1.5rem; font-weight: 600; border: none; color: #fff;
  background: linear-gradient(135deg, #2563EB, #7C3AED); box-shadow: 0 10px 24px -8px rgba(79,70,229,0.55);}
[data-testid="stFormSubmitButton"] button:hover {filter: brightness(1.08); color: #fff;}
.section-title {font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 600; color: var(--ink); margin: 1.4rem 0 0.8rem;
  display: flex; align-items: center; gap: 0.5rem;}
.section-title:before {content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--blue); box-shadow: 0 0 10px rgba(37,99,235,0.7);}
/* Agent pipeline */
.step {display: flex; gap: 1rem; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 1rem 1.2rem; margin-bottom: 0.8rem; box-shadow: var(--glow);}
.step .dot {flex: 0 0 38px; height: 38px; border-radius: 12px; background: linear-gradient(135deg, #E4EDFF, #EEE8FF); border: 1px solid var(--line-strong);
  display: flex; align-items: center; justify-content: center; font-size: 1.05rem;}
.step .body {flex: 1; min-width: 0;}
.step .head {display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem;}
.step .name {font-weight: 600; color: var(--ink);}
.step .done {color: var(--good); font-size: 0.75rem; font-weight: 600; white-space: nowrap;}
.step .role {color: var(--muted); font-size: 0.8rem; margin-bottom: 0.55rem;}
.step .out {font-family: ui-monospace, Menlo, Consolas, monospace; background: #F5F8FF; border: 1px solid var(--line); border-radius: 10px;
  padding: 0.7rem 0.9rem; word-break: break-word; font-size: 0.78rem; color: #24365F; max-height: 260px; overflow: auto;}
/* Result */
.badge {display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.4rem 1rem; border-radius: 999px; font-weight: 600; font-size: 0.9rem;}
.badge-resolved {background: var(--good-bg); color: var(--good); border: 1px solid #BFE3C4;}
.badge-escalated {background: var(--bad-bg); color: var(--bad); border: 1px solid #F2C6C6;}
.reason {color: var(--muted); font-size: 0.85rem; margin-top: 0.55rem;}
.meta {display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0;}
.meta span {background: #F5F8FF; border: 1px solid var(--line); border-radius: 999px; padding: 0.25rem 0.8rem; font-size: 0.78rem; color: var(--ink);}
.meta span b {color: var(--muted); font-weight: 500;}
.reply {background: linear-gradient(180deg, #F3F7FF, #F6F2FF); border: 1px solid var(--line-strong); border-radius: 14px; padding: 1.1rem 1.3rem;
  line-height: 1.65; color: var(--ink); font-size: 0.95rem;}
.reply p {margin: 0 0 0.7rem;} .reply p:last-child {margin: 0;}
.foot {color: var(--muted); font-size: 0.8rem; margin-top: 0.7rem;}
.handoff {margin-top: 0.9rem; background: var(--bad-bg); color: var(--bad); border-radius: 12px; padding: 0.6rem 0.9rem; font-size: 0.85rem;}
.review-head {display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;}
.review-head b {color: var(--ink); font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem;}
.complaint {color: var(--ink); font-size: 0.92rem; margin: 0.6rem 0 0.2rem;}
.pending {background: #FFF6E5; color: #9A5B00; border: 1px solid #F5D9A6; border-radius: 999px; padding: 0.25rem 0.8rem; font-size: 0.78rem; font-weight: 600;}
.empty {color: var(--muted); text-align: center; padding: 3rem 1rem; border: 1px dashed var(--line-strong); border-radius: 18px; background: var(--panel);}
/* KPI cards */
.kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; margin: 0.4rem 0 1.2rem;}
.kpi {position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 1.1rem 1.3rem; overflow: hidden; box-shadow: var(--glow);}
.kpi:before {content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: linear-gradient(90deg, #0EA5E9, #2563EB, #7C3AED);}
.kpi .top {display: flex; justify-content: space-between; align-items: center;}
.kpi .icon {width: 34px; height: 34px; border-radius: 10px; background: #EEF3FF; display: flex; align-items: center; justify-content: center; font-size: 1rem;}
.kpi .label {font-size: 0.7rem; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); font-weight: 600;}
.kpi .value {font-family: 'Space Grotesk', sans-serif; font-size: 2.3rem; font-weight: 700; color: var(--ink); line-height: 1.1; margin-top: 0.35rem;}
.kpi .sub {font-size: 0.8rem; color: var(--muted);}
.kpi .bar {height: 6px; border-radius: 999px; background: #EEF3FF; margin-top: 0.6rem; overflow: hidden;}
.kpi .bar span {display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #0EA5E9, #2563EB);}
@media (max-width: 900px) {.kpis {grid-template-columns: repeat(2, minmax(0, 1fr));} .hero h1 {font-size: 2rem;}}
[data-testid="stPlotlyChart"] {background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 0.6rem 0.4rem; box-shadow: var(--glow);}
[data-testid="stDataFrame"] {border: 1px solid var(--line); border-radius: 14px; overflow: hidden;}
</style>
"""
# Blank lines would end the HTML block in Markdown and print the CSS as text, so drop them.
st.markdown(re.sub(r"\n\s*\n", "\n", STYLE), unsafe_allow_html=True)


def load_log() -> pd.DataFrame:
    if not LOG_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(LOG_FILE, dtype=str).fillna("")
    return df.reindex(columns=COLUMNS, fill_value="")  # logs from older versions lack the newer columns


def as_paragraphs(text: str) -> str:
    """Turn plain reply text into HTML paragraphs without the large gaps of pre-wrap."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return "".join(f"<p>{html.escape(b).replace(chr(10), '<br>')}</p>" for b in blocks)


AGENT_ICONS = {"query_agent": "🧠", "knowledge_agent": "📚", "resolution_agent": "✍️", "log_agent": "🛡️"}


def step_card(number: int, source: str, content: str) -> str:
    return (
        f'<div class="step"><div class="dot">{AGENT_ICONS[source]}</div><div class="body">'
        f'<div class="head"><div class="name">{number}. {AGENT_LABELS[source]}</div><div class="done">● Done</div></div>'
        f'<div class="role">{AGENT_ROLES[source]}</div>'
        # <br> instead of raw newlines: a blank line would end the HTML block in Markdown.
        f'<div class="out">{html.escape(content.strip()).replace(chr(10), "<br>")}</div></div></div>'
    )


async def process_ticket(complaint: str, name: str, order_id: str, timeline) -> TicketOutcome | None:
    outcome = None
    step = 0
    async for item in run_ticket(complaint, name, order_id):
        if isinstance(item, TicketOutcome):
            outcome = item
            continue
        source, content = item
        step += 1  # numbered in the order the selector picked them
        timeline.markdown(step_card(step, source, content), unsafe_allow_html=True)
    return outcome


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


def render_new_ticket() -> None:
    sample = st.selectbox("Start from a sample complaint", list(SAMPLE_COMPLAINTS))
    default_complaint, default_name, default_order = SAMPLE_COMPLAINTS[sample]

    with st.form("ticket_form", border=False):
        col1, col2 = st.columns(2)
        name = col1.text_input("Customer name", value=default_name, placeholder="Optional")
        order_id = col2.text_input("Order ID", value=default_order, placeholder="ORD-1234")
        complaint = st.text_area("Complaint", value=default_complaint, height=110, placeholder="Describe the problem...")
        submitted = st.form_submit_button("Submit ticket  →")

    if not submitted:
        return
    if not complaint.strip():
        st.warning("Please enter the complaint first.")
        return

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown('<div class="section-title">Agent steps</div>', unsafe_allow_html=True)
        timeline = st.container()
    with right:
        st.markdown('<div class="section-title">Result</div>', unsafe_allow_html=True)
        result_area = st.empty()

    try:
        with st.spinner("The agents are working on this ticket..."):
            outcome = asyncio.run(process_ticket(complaint, name, order_id, timeline))
    except Exception as exc:  # show API/config problems in the UI instead of a stack trace
        st.error(f"Something went wrong while running the agents: {exc}")
        return

    if outcome is None or not outcome.ticket_id:
        result_area.error("The Log Agent did not record this ticket. Check the agent steps for details.")
        return
    result_area.markdown(result_card(outcome), unsafe_allow_html=True)


def render_log() -> None:
    df = load_log()
    if df.empty:
        st.markdown('<div class="empty">No tickets yet. Submit one in the New ticket tab.</div>', unsafe_allow_html=True)
        return

    col1, col2, col3 = st.columns([1, 1, 2])
    status = col1.multiselect("Status", ["Resolved", "Escalated"])
    categories = col2.multiselect("Category", sorted(df["category"].unique()))
    search = col3.text_input("Search complaints", placeholder="e.g. refund")

    view = df
    if status:
        view = view[view["status"].isin(status)]
    if categories:
        view = view[view["category"].isin(categories)]
    if search:
        view = view[view["complaint"].str.contains(search, case=False, regex=False)]

    st.caption(f"Showing {len(view)} of {len(df)} tickets")
    st.dataframe(
        view.iloc[::-1],
        hide_index=True,
        width="stretch",
        column_config={
            "complaint": st.column_config.TextColumn(width="large"),
            "response": st.column_config.TextColumn(width="large"),
        },
    )

    excel = io.BytesIO()
    df.to_excel(excel, index=False, sheet_name="tickets")
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), "tickets.csv", "text/csv")
    d2.download_button(
        "Download Excel",
        excel.getvalue(),
        "tickets.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def render_approvals() -> None:
    df = load_log()
    pending = df[df["review_status"] == PENDING]
    reviewed = df[(df["status"] == "Escalated") & (df["review_status"] != PENDING)]
    st.markdown(
        '<div class="section-title">Escalated replies waiting for a human</div>'
        '<p style="color:var(--muted);margin-top:-0.4rem">A support person checks each escalated reply. '
        "The decision goes through AutoGen's UserProxyAgent and is saved to the ticket log.</p>",
        unsafe_allow_html=True,
    )
    if pending.empty:
        st.markdown('<div class="empty">Nothing to approve. Every escalated reply has been reviewed.</div>', unsafe_allow_html=True)

    for _, ticket in pending.iloc[::-1].iterrows():
        tid = ticket["ticket_id"]
        with st.container(border=True):
            st.markdown(
                f'<div class="review-head"><b>{html.escape(tid)} · {html.escape(ticket["customer_name"] or "Customer")}</b>'
                f'<span class="pending">⏳ {PENDING}</span></div>'
                f'<div class="meta"><span><b>Category</b> {html.escape(ticket["category"] or "-")}</span>'
                f'<span><b>Urgency</b> {html.escape(ticket["urgency"] or "-")}</span>'
                f'<span><b>Sentiment</b> {html.escape(ticket["sentiment"] or "-")}</span>'
                f'<span><b>Language</b> {html.escape(ticket["language"] or "-")}</span></div>'
                f'<div class="reason">Escalated because: {html.escape(ticket["escalation_reason"] or "-")}</div>'
                f'<div class="complaint"><b>Complaint:</b> {html.escape(ticket["complaint"])}</div>',
                unsafe_allow_html=True,
            )
            reply = st.text_area("Reply to customer (edit if needed)", ticket["response"], height=180, key=f"reply_{tid}")
            c1, c2 = st.columns([1, 2])
            reviewer = c1.text_input("Reviewer", value=st.session_state.get("reviewer_name", ""), placeholder="Your name", key=f"who_{tid}")
            note = c2.text_input("Note (needed to reject)", key=f"note_{tid}", placeholder="Why the reply should not be sent")
            b1, b2, _ = st.columns([1, 1, 2])
            decision = None
            if b1.button("✓ Approve and send", key=f"ok_{tid}", type="primary"):
                decision = "APPROVE" if reply.strip() == ticket["response"].strip() else f"EDIT {reply}"
            if b2.button("✕ Reject", key=f"no_{tid}"):
                if note.strip():
                    decision = f"REJECT {note}"
                else:
                    st.warning("Add a note explaining why the reply is rejected.")
            if decision:
                st.session_state["reviewer_name"] = reviewer
                # The UserProxyAgent asks for input; the support person's click is the answer.
                status = asyncio.run(review_ticket(ticket.to_dict(), input_func=lambda _prompt: decision, reviewer=reviewer))
                st.session_state["review_done"] = f"{tid}: {status}"
                st.rerun()

    if done := st.session_state.pop("review_done", None):
        st.success(f"Saved. {done}")
    if not reviewed.empty:
        st.markdown('<div class="section-title" style="margin-top:1.4rem">Reviewed</div>', unsafe_allow_html=True)
        st.dataframe(
            reviewed.iloc[::-1][["ticket_id", "customer_name", "category", "review_status", "reviewer", "reviewed_at", "final_response"]],
            hide_index=True,
            width="stretch",
            column_config={"final_response": st.column_config.TextColumn("reply sent", width="large")},
        )


def _layout(fig: go.Figure, title: str, subtitle: str = "", height: int = 330) -> go.Figure:
    heading = f"<b>{title}</b>" + (f"<br><span style='font-size:12px;color:{MUTED}'>{subtitle}</span>" if subtitle else "")
    fig.update_layout(
        title=dict(text=heading, x=0.03, y=0.93, font=dict(family="Space Grotesk, sans-serif", size=16, color=INK)),
        font=dict(family="Inter, sans-serif", size=12, color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=28, t=86, b=16),
        height=height,
        showlegend=False,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=BLUE, font=dict(family="Inter, sans-serif", color=INK)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, ticks="", tickfont=dict(color=INK))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, ticks="", linecolor="rgba(0,0,0,0)", rangemode="tozero")
    return fig


def _hbar(counts: pd.Series, title: str, subtitle: str, color, unit: str = "tickets") -> go.Figure:
    """Horizontal bars with a fixed bar thickness, so a single bar never turns into a huge block."""
    fig = go.Figure(
        go.Bar(
            x=counts.values, y=counts.index, orientation="h", width=0.55,
            marker=dict(color=color, cornerradius=6), text=counts.values, textposition="outside",
            textfont=dict(color=INK, size=12), cliponaxis=False, hovertemplate="%{y}: %{x} " + unit + "<extra></extra>",
        )
    )
    fig = _layout(fig, title, subtitle, height=max(230, 120 + 46 * len(counts)))
    fig.update_xaxes(showticklabels=False, linecolor="rgba(0,0,0,0)", range=[0, counts.max() * 1.18 + 0.5])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK))
    return fig


def kpi_card(icon: str, label: str, value: str, sub: str, share: float | None = None) -> str:
    bar = f'<div class="bar"><span style="width:{share * 100:.0f}%"></span></div>' if share is not None else ""
    return (
        f'<div class="kpi"><div class="top"><div class="label">{label}</div><div class="icon">{icon}</div></div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div>{bar}</div>'
    )


CHART_CONFIG = {"displayModeBar": False}


def render_dashboard() -> None:
    df = load_log()
    if df.empty:
        st.markdown('<div class="empty">The dashboard fills in once tickets are logged.</div>', unsafe_allow_html=True)
        return

    total = len(df)
    escalated = int((df["status"] == "Escalated").sum())
    resolved = total - escalated
    awaiting = int((df["review_status"] == PENDING).sum())
    urgency_score = df["urgency"].map({"Low": 1, "Medium": 2, "High": 3}).dropna()
    avg_urgency = urgency_score.mean() if not urgency_score.empty else 0
    avg_label = "Low" if avg_urgency < 1.5 else "Medium" if avg_urgency < 2.5 else "High"
    st.markdown(
        '<div class="kpis">'
        + kpi_card("🎫", "Total tickets", str(total), "handled by the agent team")
        + kpi_card("🤖", "Resolved by AI", str(resolved), f"{resolved / total:.0%} automation rate", resolved / total)
        + kpi_card("🧑‍💼", "Escalated", str(escalated), f"{escalated / total:.0%} sent to humans · {awaiting} awaiting approval", escalated / total)
        + kpi_card("⚡", "Average urgency", f"{avg_urgency:.1f}", f"{avg_label} on a 1–3 scale", avg_urgency / 3)
        + "</div>",
        unsafe_allow_html=True,
    )

    # Row 1: volume over time (full width)
    times = pd.to_datetime(df["timestamp"], errors="coerce").dropna().sort_values()
    if not times.empty:
        span = times.iloc[-1] - times.iloc[0]
        if span <= pd.Timedelta(hours=3):
            freq, label = "10min", "%H:%M"
        elif span <= pd.Timedelta(days=2):
            freq, label = "1h", "%d %b %H:00"
        else:
            freq, label = "1D", "%d %b"
        volume = times.dt.floor(freq).value_counts().sort_index()
        full_index = pd.date_range(volume.index.min(), volume.index.max(), freq=freq)
        volume = volume.reindex(full_index, fill_value=0)
        fig = go.Figure(
            go.Scatter(
                x=volume.index, y=volume.values, mode="lines+markers", line=dict(color=BLUE, width=2),
                marker=dict(size=8, color="#FFFFFF", line=dict(color=BLUE, width=2)), fill="tozeroy",
                fillcolor="rgba(42,120,214,0.12)", hovertemplate="%{x|" + label + "}: %{y} tickets<extra></extra>",
            )
        )
        fig = _layout(fig, "Ticket volume", "Tickets received over time", height=290)
        if len(volume) <= 14:
            pad = pd.Timedelta(freq) / 3  # a third of a bucket on each side
            fig.update_xaxes(
                tickvals=volume.index, ticktext=[t.strftime(label) for t in volume.index],
                range=[volume.index[0] - pad, volume.index[-1] + pad],
            )
        else:
            fig.update_xaxes(tickformat=label)
        fig.update_yaxes(tickformat=",d", dtick=max(1, int(volume.max() // 4) or 1))
        st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

    # Row 2: categories and how each one resolved
    c1, c2 = st.columns(2, gap="medium")
    by_category = df.groupby("category").size().sort_values()
    c1.plotly_chart(_hbar(by_category, "Tickets by category", "What customers contact us about", BLUE), width="stretch", config=CHART_CONFIG)

    # AI resolution rate per category: one bar on a light 0-100% track, with "x of y" beside it.
    resolved_by_cat = df[df["status"] == "Resolved"].groupby("category").size().reindex(by_category.index, fill_value=0)
    rate = (resolved_by_cat / by_category).sort_values(kind="stable")
    resolved_by_cat, totals = resolved_by_cat[rate.index], by_category[rate.index]
    labels = [f"<b>{r:.0%}</b>  ·  {n} of {t}" for r, n, t in zip(rate, resolved_by_cat, totals)]
    fig = go.Figure()
    fig.add_bar(
        y=rate.index, x=[1] * len(rate), orientation="h", width=0.5, marker=dict(color="#EAF0FD", cornerradius=8),
        text=labels, textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False, hoverinfo="skip",
    )
    fig.add_bar(
        y=rate.index, x=rate.values, orientation="h", width=0.5, customdata=list(zip(resolved_by_cat, totals)),
        marker=dict(color=[rate_color(r) for r in rate], cornerradius=8),
        hovertemplate="%{y}: %{customdata[0]} of %{customdata[1]} resolved by AI (%{x:.0%})<extra></extra>",
    )
    fig.update_layout(barmode="overlay")
    fig = _layout(fig, "AI resolution rate", "Share of each category solved without a human", height=max(230, 120 + 46 * len(rate)))
    fig.update_xaxes(range=[0, 1.42], showticklabels=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK))
    c2.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

    # Row 3: urgency, sentiment, escalation reasons
    c3, c4, c5 = st.columns(3, gap="medium")
    by_urgency = df["urgency"].value_counts().reindex(list(URGENCY_COLORS), fill_value=0)
    fig = go.Figure(
        go.Bar(
            x=by_urgency.index, y=by_urgency.values, width=0.5, marker=dict(color=list(URGENCY_COLORS.values()), cornerradius=6),
            text=by_urgency.values, textposition="outside", textfont=dict(color=INK), cliponaxis=False,
            hovertemplate="%{x} urgency: %{y} tickets<extra></extra>",
        )
    )
    fig = _layout(fig, "Urgency", "How pressing tickets are", height=300)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, by_urgency.max() * 1.25 + 0.5])
    c3.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

    present = [s for s in SENTIMENT_COLORS if s in set(df["sentiment"])]
    if present:
        by_sentiment = df["sentiment"].value_counts().reindex(present[::-1], fill_value=0)
        colors = [SENTIMENT_COLORS[s] for s in by_sentiment.index]
        fig = _hbar(by_sentiment, "Customer mood", "Sentiment detected by the Query Agent", colors)
        fig.update_layout(height=300)
        c4.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

    reasons = df.loc[df["escalation_reason"] != "", "escalation_reason"].str.split(r" \+ ").explode().str.strip()
    reason_counts = reasons.value_counts().sort_values().tail(5)
    if reason_counts.empty:
        c5.markdown('<div class="empty">No escalations yet.<br>Every ticket so far was resolved by AI.</div>', unsafe_allow_html=True)
    else:
        fig = _hbar(reason_counts, "Escalation reasons", "Why tickets went to a human", VIOLET)
        fig.update_layout(height=300)
        c5.plotly_chart(fig, width="stretch", config=CHART_CONFIG)


with st.sidebar:
    st.markdown(
        '<div class="side-brand"><div class="logo">✦</div><div class="name">ShopNest AI<small>Autonomous Support Desk</small></div></div>'
        '<div class="side-status">4 agents online · 1 human reviewer</div>'
        '<div class="side-label">Agent team</div>'
        + "".join(
            f'<div class="side-agent"><div class="num">{i}</div><div class="txt"><b>{AGENT_LABELS[a]}</b>'
            f"<small>{AGENT_ROLES[a]}</small></div></div>"
            for i, a in enumerate(AGENT_STEPS, start=1)
        )
        + '<div class="side-agent"><div class="num">👤</div><div class="txt"><b>Support reviewer (human)</b>'
        "<small>Approves, edits or rejects escalated replies via UserProxyAgent</small></div></div>"
        + '<div class="side-label">Knowledge base · ChromaDB</div>',
        unsafe_allow_html=True,
    )
    for path in sorted(KB_DIR.glob("*.md")):
        with st.expander(path.stem.replace("_", " ").title()):
            st.markdown(path.read_text(encoding="utf-8"))


def hero_network() -> str:
    """The AI brain in the middle, wired to the four agents. Inline SVG, animated with CSS."""
    nodes = [
        ("query_agent", 40, 28, "🧠", "Understands the request"),
        ("knowledge_agent", 40, 212, "📚", "Retrieves policy"),
        ("resolution_agent", 740, 28, "✍️", "Writes the reply"),
        ("log_agent", 740, 212, "🛡️", "Logs and escalates"),
    ]
    parts = [
        '<svg viewBox="0 0 1000 330" xmlns="http://www.w3.org/2000/svg">',
        '<defs><radialGradient id="orb" cx="50%" cy="45%" r="55%"><stop offset="0%" stop-color="#93C5FD"/>'
        '<stop offset="35%" stop-color="#3B82F6"/><stop offset="75%" stop-color="#1E3A8A"/><stop offset="100%" stop-color="#0B1633"/></radialGradient>'
        '<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#3B82F6" stop-opacity="0.55"/>'
        '<stop offset="100%" stop-color="#3B82F6" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="wire" x1="0" x2="1"><stop offset="0%" stop-color="#38BDF8"/><stop offset="100%" stop-color="#8B5CF6"/></linearGradient></defs>',
    ]
    for _, x, y, _, _ in nodes:
        sx = x + 220 if x < 500 else x
        sy = y + 45
        cx = 500 + (-58 if x < 500 else 58)
        cy = 165 + (-24 if y < 100 else 24)
        mid = (sx + cx) / 2
        parts.append(
            f'<path d="M{sx},{sy} C{mid},{sy} {mid},{cy} {cx},{cy}" stroke="url(#wire)" stroke-width="1.6" fill="none" opacity="0.35"/>'
            f'<path class="flow" d="M{sx},{sy} C{mid},{sy} {mid},{cy} {cx},{cy}" stroke="#7DD3FC" stroke-width="1.6" fill="none"/>'
            f'<circle cx="{sx}" cy="{sy}" r="4" fill="#38BDF8"/>'
        )
    parts.append(
        '<circle cx="500" cy="165" r="120" fill="url(#halo)"/>'
        '<circle class="orb-ring" cx="500" cy="165" r="86" fill="none" stroke="#60A5FA" stroke-width="1"/>'
        '<circle cx="500" cy="165" r="70" fill="url(#orb)" stroke="#93C5FD" stroke-width="1.5"/>'
        '<text x="500" y="160" text-anchor="middle" font-size="34" fill="#fff">✦</text>'
        '<text x="500" y="190" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-size="13" font-weight="600" fill="#E0F2FE" letter-spacing="2">AI BRAIN</text>'
        '<text x="500" y="265" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="#8FA3C8">Claude · AutoGen orchestration</text>'
    )
    for key, x, y, icon, caption in nodes:
        parts.append(
            f'<rect x="{x}" y="{y}" width="220" height="90" rx="14" fill="#0D1B3E" fill-opacity="0.85" stroke="#3B82F6" stroke-opacity="0.45"/>'
            f'<rect x="{x + 16}" y="{y + 22}" width="44" height="44" rx="11" fill="#1E3A8A" fill-opacity="0.7" stroke="#60A5FA" stroke-opacity="0.5"/>'
            f'<text x="{x + 38}" y="{y + 52}" text-anchor="middle" font-size="20">{icon}</text>'
            f'<text x="{x + 74}" y="{y + 40}" font-family="Space Grotesk, sans-serif" font-size="14" font-weight="600" fill="#E6EEFF">{AGENT_LABELS[key].replace(" Agent", "")}</text>'
            f'<text x="{x + 74}" y="{y + 60}" font-family="Inter, sans-serif" font-size="11.5" fill="#8FA3C8">{caption}</text>'
            f'<circle cx="{x + 200}" cy="{y + 18}" r="4" fill="#34D399"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


st.markdown(
    '<div class="hero"><div class="eyebrow">Multi-agent AI · ShopNest support</div>'
    '<h1>AI agents, built into <span class="grad">customer support</span></h1>'
    "<p>An AI brain picks which of four specialist agents acts next. They read each complaint, answer it from company policy "
    "in the customer's own language, and log it in seconds, handing difficult cases to a human for approval.</p>"
    + hero_network()
    + '<div class="secure"><span>🔒 Answers only from company documents · every ticket audited</span></div></div>',
    unsafe_allow_html=True,
)

# Fixed labels: a label that changes (like a live count) would make Streamlit jump back to the first tab.
tab_new, tab_review, tab_log, tab_dash = st.tabs(["New ticket", "Approvals", "Ticket log", "Dashboard"])
with tab_new:
    render_new_ticket()
with tab_review:
    render_approvals()
with tab_log:
    render_log()
with tab_dash:
    render_dashboard()
