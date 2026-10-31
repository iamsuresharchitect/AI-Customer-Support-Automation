"""ShopNest AI Support Desk - Streamlit UI.

    streamlit run app.py
"""

import asyncio
import html
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from agents.knowledge_agent import KB_DIR
from agents.log_agent import COLUMNS, LOG_FILE
from team import AGENT_LABELS, TicketOutcome, run_ticket

st.set_page_config(page_title="ShopNest AI Support Desk", page_icon="🎧", layout="wide")

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
}

AGENT_ICONS = {"query_agent": "🔎", "knowledge_agent": "📚", "resolution_agent": "✍️", "log_agent": "🗂️"}

# Chart colors from the validated reference palette: one blue for single series,
# status colors (always shown with a label) for Resolved / Escalated.
BLUE = "#2a78d6"
STATUS_COLORS = {"Resolved": "#0ca30c", "Escalated": "#d03b3b"}
URGENCY_COLORS = {"Low": "#86b6ef", "Medium": "#2a78d6", "High": "#104281"}

st.markdown(
    """
<style>
.reply-box {border-left: 5px solid #2a78d6; background: rgba(42,120,214,0.08); padding: 1rem 1.2rem;
            border-radius: 6px; white-space: pre-wrap; line-height: 1.55;}
.badge {display: inline-block; padding: 0.25rem 0.8rem; border-radius: 999px; font-weight: 600; color: #fff;}
.badge-resolved {background: #0b7f0b;}
.badge-escalated {background: #c03030;}
</style>
""",
    unsafe_allow_html=True,
)


def load_log() -> pd.DataFrame:
    if not LOG_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(LOG_FILE, dtype=str).fillna("")


def status_badge(status: str, reason: str = "") -> str:
    css = "badge-escalated" if status == "Escalated" else "badge-resolved"
    icon = "⚠️" if status == "Escalated" else "✅"
    reason_html = f" &nbsp;<span>{html.escape(reason)}</span>" if reason else ""
    return f'<span class="badge {css}">{icon} {html.escape(status)}</span>{reason_html}'


async def process_ticket(complaint: str, name: str, order_id: str, timeline) -> TicketOutcome | None:
    outcome = None
    async for item in run_ticket(complaint, name, order_id):
        if isinstance(item, TicketOutcome):
            outcome = item
            continue
        source, content = item
        with timeline:
            with st.expander(f"{AGENT_ICONS[source]} {AGENT_LABELS[source]}", expanded=source != "knowledge_agent"):
                st.code(content, language=None, wrap_lines=True)
    return outcome


def render_new_ticket() -> None:
    sample = st.selectbox("Start from a sample complaint (optional)", list(SAMPLE_COMPLAINTS))
    default_complaint, default_name, default_order = SAMPLE_COMPLAINTS[sample]

    with st.form("ticket_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("Customer name", value=default_name)
        order_id = col2.text_input("Order ID", value=default_order, placeholder="ORD-1234")
        complaint = st.text_area("Complaint", value=default_complaint, height=120, placeholder="Describe the problem...")
        submitted = st.form_submit_button("Submit ticket", type="primary")

    if not submitted:
        return
    if not complaint.strip():
        st.warning("Please enter the complaint first.")
        return

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Agent steps")
        timeline = st.container()
    with right:
        st.subheader("Result")
        result_area = st.container()

    try:
        with st.spinner("The agents are working on this ticket..."):
            outcome = asyncio.run(process_ticket(complaint, name, order_id, timeline))
    except Exception as exc:  # show API/config problems in the UI instead of a stack trace
        st.error(f"Something went wrong while running the agents: {exc}")
        return

    with result_area:
        if outcome is None or not outcome.ticket_id:
            st.error("The Log Agent did not record this ticket. Check the agent steps for details.")
            return
        st.markdown(status_badge(outcome.status, outcome.escalation_reason), unsafe_allow_html=True)
        st.caption(f"Ticket {outcome.ticket_id}")
        st.markdown(
            f"**Category:** {outcome.category or '-'} &nbsp;·&nbsp; **Urgency:** {outcome.urgency or '-'}"
            f" &nbsp;·&nbsp; **Sentiment:** {outcome.sentiment or '-'}"
        )
        st.markdown("**Reply to customer**")
        st.markdown(f'<div class="reply-box">{html.escape(outcome.reply)}</div>', unsafe_allow_html=True)
        st.caption(f"Sources: {outcome.used_sources or 'NONE'} · Confidence: {outcome.confidence or '-'}")
        if outcome.status == "Escalated":
            st.info("This ticket has been handed to human support.")


def render_log() -> None:
    df = load_log()
    if df.empty:
        st.info("No tickets yet. Submit one in the New ticket tab.")
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
        use_container_width=True,
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


def _style(fig):
    fig.update_layout(
        margin=dict(l=10, r=10, t=70, b=10),
        height=340,
        bargap=0.35,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


def render_dashboard() -> None:
    df = load_log()
    if df.empty:
        st.info("The dashboard fills in once tickets are logged.")
        return

    total = len(df)
    escalated = int((df["status"] == "Escalated").sum())
    urgency_score = df["urgency"].map({"Low": 1, "Medium": 2, "High": 3}).dropna()
    avg_urgency = urgency_score.mean() if not urgency_score.empty else 0
    avg_label = "Low" if avg_urgency < 1.5 else "Medium" if avg_urgency < 2.5 else "High"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total tickets", total)
    k2.metric("Resolved", total - escalated)
    k3.metric("Escalated", escalated, f"{escalated / total:.0%} of tickets", delta_color="off")
    k4.metric("Average urgency", f"{avg_urgency:.1f} / 3", avg_label, delta_color="off")

    c1, c2 = st.columns(2)
    by_category = df.groupby("category").size().sort_values().reset_index(name="tickets")
    fig = px.bar(by_category, x="tickets", y="category", orientation="h", title="Tickets per category", text="tickets")
    fig.update_traces(marker_color=BLUE, textposition="outside", cliponaxis=False)
    fig.update_layout(yaxis_title=None, xaxis_title=None)
    c1.plotly_chart(_style(fig), use_container_width=True)

    by_status = df.groupby(["category", "status"]).size().reset_index(name="tickets")
    fig = px.bar(
        by_status,
        x="category",
        y="tickets",
        color="status",
        title="Resolved vs escalated by category",
        color_discrete_map=STATUS_COLORS,
        category_orders={"status": ["Resolved", "Escalated"]},
    )
    fig.update_traces(marker_line_width=2, marker_line_color="rgba(0,0,0,0)")
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    c2.plotly_chart(_style(fig), use_container_width=True)

    c3, c4 = st.columns(2)
    by_urgency = (
        df[df["urgency"].isin(URGENCY_COLORS)]
        .groupby("urgency")
        .size()
        .reindex(list(URGENCY_COLORS), fill_value=0)
        .reset_index(name="tickets")
    )
    fig = px.bar(
        by_urgency, x="urgency", y="tickets", color="urgency", title="Tickets by urgency",
        color_discrete_map=URGENCY_COLORS, text="tickets",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
    c3.plotly_chart(_style(fig), use_container_width=True)

    df["date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.strftime("%d %b")
    by_day = df.groupby("date", sort=False).size().reset_index(name="tickets")
    fig = px.bar(by_day, x="date", y="tickets", title="Tickets per day")
    fig.update_traces(marker_color=BLUE)
    fig.update_layout(xaxis_title=None, yaxis_title=None, xaxis_type="category")
    c4.plotly_chart(_style(fig), use_container_width=True)

    with st.expander("Escalation reasons"):
        reasons = df.loc[df["escalation_reason"] != "", "escalation_reason"].str.split(r" \+ ").explode()
        st.dataframe(reasons.value_counts().rename_axis("reason").reset_index(name="tickets"), hide_index=True)


with st.sidebar:
    st.title("🎧 ShopNest Support Desk")
    st.caption("Four AutoGen agents powered by Claude")
    st.markdown(
        "1. **Customer Query Agent** classifies the complaint\n"
        "2. **Knowledge Base Agent** searches company docs (ChromaDB)\n"
        "3. **Resolution Agent** writes a grounded reply\n"
        "4. **Log Agent** records the ticket and escalates hard cases"
    )
    st.divider()
    st.markdown("**Knowledge base**")
    for path in sorted(KB_DIR.glob("*.md")):
        with st.expander(path.name):
            st.markdown(path.read_text(encoding="utf-8"))

st.title("AI Customer Support Desk")
tab_new, tab_log, tab_dash = st.tabs(["New ticket", "Ticket log", "Dashboard"])
with tab_new:
    render_new_ticket()
with tab_log:
    render_log()
with tab_dash:
    render_dashboard()
