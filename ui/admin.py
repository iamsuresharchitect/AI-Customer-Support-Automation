"""Admin panel: dashboard, ticket status, approvals, knowledge base, users, ticket log and the agent console."""

import asyncio
import html
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
from agents.knowledge_agent import KB_DIR, TOPICS, load_sections, search_passages
from agents.log_agent import PENDING
from agents.review_agent import review_ticket
from team import AGENT_LABELS
from ui.common import AGENT_ICONS, AGENT_ROLES, AGENT_STEPS, load_log, process_ticket, result_card, step_card
from ui.common import logout_button, pipeline_html
from ui.theme import BLUE, GRID, INK, MUTED, ORANGE, SENTIMENT_COLORS, URGENCY_COLORS, rate_color

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

def render_console() -> None:
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
        flow = st.empty()
        flow.markdown(pipeline_html(set(), "query_agent"), unsafe_allow_html=True)
        timeline = st.container()
    with right:
        st.markdown('<div class="section-title">Result</div>', unsafe_allow_html=True)
        result_area = st.empty()

    finished = set()

    def on_step(number: int, source: str, content: str) -> None:
        finished.add(source)
        flow.markdown(pipeline_html(finished, next((a for a in AGENT_STEPS if a not in finished), None)), unsafe_allow_html=True)
        timeline.markdown(step_card(number, source, content), unsafe_allow_html=True)

    try:
        with st.spinner("The agents are working on this ticket..."):
            outcome = asyncio.run(
                process_ticket(complaint, name, order_id, lambda n, src, txt: on_step(n, src, txt))
            )
    except Exception as exc:  # show API/config problems in the UI instead of a stack trace
        st.error(f"Something went wrong while running the agents: {exc}")
        return

    if outcome is None or not outcome.ticket_id:
        result_area.error("The Log Agent did not record this ticket. Check the agent steps for details.")
        return
    flow.markdown(pipeline_html(set(AGENT_STEPS), None, f"Ticket {outcome.ticket_id} · {outcome.status}", finished=True), unsafe_allow_html=True)
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
        title=dict(text=heading, x=0.03, y=0.93, font=dict(family="Roboto, Arial, sans-serif", size=16, color=INK)),
        font=dict(family="Roboto, Arial, sans-serif", size=12, color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=28, t=86, b=16),
        height=height,
        showlegend=False,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=BLUE, font=dict(family="Roboto, Arial, sans-serif", color=INK)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, ticks="", tickfont=dict(color=INK))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, ticks="", linecolor="rgba(0,0,0,0)", rangemode="tozero")
    return fig


def kpi_card(icon: str, label: str, value: str, sub: str, share: float | None = None) -> str:
    bar = f'<div class="bar"><span style="width:{share * 100:.0f}%"></span></div>' if share is not None else ""
    return (
        f'<div class="kpi"><div class="top"><div class="label">{label}</div><div class="icon">{icon}</div></div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div>{bar}</div>'
    )


CHART_CONFIG = {"displayModeBar": False}
CATEGORY_ICONS = {"Shipping": "🚚", "Refund": "💸", "Account": "👤", "Product": "📦", "Billing": "💳", "Other": "❓"}
MOOD_ICONS = {"Positive": "😊", "Neutral": "😐", "Frustrated": "😕", "Angry": "😠", "Very Angry": "😡"}
LANG_SCRIPTS = {"English": "Aa", "Tamil": "த", "Malayalam": "മ", "Telugu": "తె", "Hindi": "हि"}


def ring(value: float, label: str, caption: str, color: str = "#FFE11B", text: str | None = None) -> str:
    """Animated SVG ring gauge (value 0-1) for the hero banner."""
    circ = 2 * 3.14159 * 42
    offset = circ * (1 - max(0.0, min(1.0, value)))
    return (
        f'<div class="ring" title="{html.escape(label)}: {html.escape(text or f"{value:.0%}")}">'
        f'<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="42" class="track"/>'
        f'<circle cx="50" cy="50" r="42" class="arc" stroke="{color}" style="stroke-dasharray:{circ:.1f};stroke-dashoffset:{offset:.1f};--c:{circ:.1f}"/></svg>'
        f'<div class="ring-val">{html.escape(text or f"{value:.0%}")}</div>'
        f'<div class="ring-label">{html.escape(label)}</div><div class="ring-cap">{html.escape(caption)}</div></div>'
    )


def bar_row(label: str, count: int, total: int, icon: str = "", color: str = BLUE, delay: float = 0) -> str:
    share = count / total if total else 0
    return (
        f'<div class="ib-row" title="{html.escape(label)}: {count} of {total} ({share:.0%})">'
        f'<div class="ib-label">{icon} {html.escape(label)}</div>'
        f'<div class="ib-track"><span style="width:{share * 100:.1f}%;background:{color};animation-delay:{delay:.2f}s"></span></div>'
        f'<div class="ib-val"><b>{count}</b> · {share:.0%}</div></div>'
    )


def render_dashboard() -> None:
    df = load_log()
    if df.empty:
        st.markdown('<div class="empty">The dashboard fills in once tickets are logged.</div>', unsafe_allow_html=True)
        return

    total = len(df)
    escalated = int((df["status"] == "Escalated").sum())
    resolved = total - escalated
    awaiting = int((df["review_status"] == PENDING).sum())
    approved = int(df["review_status"].isin(["Approved", "Edited"]).sum())
    with_sources = int(((df["kb_sources"] != "") & (df["kb_sources"].str.upper() != "NONE")).sum())
    urgency_score = df["urgency"].map({"Low": 1, "Medium": 2, "High": 3}).dropna()
    avg_urgency = urgency_score.mean() if not urgency_score.empty else 0
    avg_label = "Low" if avg_urgency < 1.5 else "Medium" if avg_urgency < 2.5 else "High"

    # Hero: the headline numbers as animated ring gauges.
    st.markdown(
        '<div class="dash-hero"><div class="hero-main"><div class="hero-kicker">Support at a glance</div>'
        f'<div class="hero-num">{total}</div><div class="hero-sub">tickets handled by the AutoGen agent team</div>'
        f'<div class="hero-chips"><span>✓ {resolved} resolved by AI</span><span>⚠ {escalated} escalated</span><span>⏳ {awaiting} awaiting approval</span></div></div>'
        '<div class="hero-rings">'
        + ring(resolved / total, "Automation rate", "solved without a human")
        + ring(with_sources / total, "Grounded answers", "replies backed by a policy document", "#B9F6CA")
        + ring(avg_urgency / 3, "Average urgency", f"{avg_label} on a 1-3 scale", "#FFB38A", f"{avg_urgency:.1f}")
        + "</div></div>",
        unsafe_allow_html=True,
    )

    # Journey: how tickets flow through the agents to a final answer.
    steps = [
        ("📥", "Received", total, "complaints in"),
        ("🧠", "Understood", int((df["category"] != "").sum()), "category, urgency, mood"),
        ("📚", "Policy found", with_sources, "matching documents"),
        ("🤖", "Answered by AI", resolved, "sent straight away"),
        ("🧑‍💼", "Human review", escalated, f"{approved} approved · {awaiting} waiting"),
    ]
    cards = []
    for i, (icon, label, value, caption) in enumerate(steps):
        share = value / total if total else 0
        cards.append(
            f'<div class="jr-step" style="animation-delay:{i * 0.12:.2f}s" title="{label}: {value} of {total}"><div class="jr-ic">{icon}</div>'
            f'<div class="jr-val">{value}</div><div class="jr-label">{label}</div><div class="jr-cap">{html.escape(caption)}</div>'
            f'<div class="jr-bar"><span style="width:{share * 100:.0f}%"></span></div></div>'
        )
    st.markdown('<div class="dash-title">Ticket journey</div><div class="journey">' + '<div class="jr-arrow">›</div>'.join(cards) + "</div>",
                unsafe_allow_html=True)

    # Category tiles: volume and how much of each the AI resolves on its own.
    by_category = df["category"].replace("", "Other").value_counts()
    tiles = []
    for i, (cat, count) in enumerate(by_category.items()):
        cat_df = df[df["category"].replace("", "Other") == cat]
        rate = (cat_df["status"] == "Resolved").mean()
        tiles.append(
            f'<div class="cat-tile" style="animation-delay:{i * 0.08:.2f}s" title="{cat}: {count} tickets, {rate:.0%} resolved by AI">'
            f'<div class="cat-top"><span class="cat-ic">{CATEGORY_ICONS.get(cat, "🏷️")}</span><span class="cat-share">{count / total:.0%}</span></div>'
            f'<div class="cat-num">{count}</div><div class="cat-name">{html.escape(cat)}</div>'
            f'<div class="cat-rate"><div class="ib-track"><span style="width:{rate * 100:.0f}%;background:{rate_color(rate)}"></span></div>'
            f'<small>{rate:.0%} solved by AI</small></div></div>'
        )
    st.markdown('<div class="dash-title">What customers contact us about</div><div class="cat-grid">' + "".join(tiles) + "</div>",
                unsafe_allow_html=True)

    # Volume trend (interactive line chart with hover).
    times = pd.to_datetime(df["timestamp"], errors="coerce").dropna().sort_values()
    left, right = st.columns([1.6, 1], gap="medium")
    if not times.empty:
        span = times.iloc[-1] - times.iloc[0]
        if span <= pd.Timedelta(hours=3):
            freq, label = "10min", "%H:%M"
        elif span <= pd.Timedelta(days=2):
            freq, label = "1h", "%d %b %H:00"
        else:
            freq, label = "1D", "%d %b"
        volume = times.dt.floor(freq).value_counts().sort_index()
        volume = volume.reindex(pd.date_range(volume.index.min(), volume.index.max(), freq=freq), fill_value=0)
        fig = go.Figure(
            go.Scatter(
                x=volume.index, y=volume.values, mode="lines+markers", line=dict(color=BLUE, width=2, shape="spline", smoothing=0.3),
                marker=dict(size=8, color="#FFFFFF", line=dict(color=BLUE, width=2)), fill="tozeroy",
                fillgradient=dict(type="vertical", colorscale=[[0, "rgba(40,116,240,0)"], [1, "rgba(40,116,240,0.28)"]]),
                hovertemplate="%{x|" + label + "}: %{y} tickets<extra></extra>",
            )
        )
        fig = _layout(fig, "Ticket volume", "Tickets received over time", height=300)
        if len(volume) <= 14:
            pad = pd.Timedelta(freq) / 3
            fig.update_xaxes(tickvals=volume.index, ticktext=[t.strftime(label) for t in volume.index],
                             range=[volume.index[0] - pad, volume.index[-1] + pad])
        else:
            fig.update_xaxes(tickformat=label)
        fig.update_yaxes(tickformat=",d", dtick=max(1, int(volume.max() // 4) or 1))
        with left, st.container(border=True, key="dash_volume"):
            st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

    # Urgency as one segmented bar, with a legend.
    by_urgency = df["urgency"].value_counts().reindex(list(URGENCY_COLORS), fill_value=0)
    segments = "".join(
        f'<span title="{u}: {n} tickets ({n / total:.0%})" style="flex:{n};background:{URGENCY_COLORS[u]}"></span>'
        for u, n in by_urgency.items() if n
    )
    legend = "".join(
        f'<div class="lg"><i style="background:{URGENCY_COLORS[u]}"></i>{u}<b>{n}</b></div>' for u, n in by_urgency.items()
    )
    languages = df["language"].replace("", "English").value_counts()
    lang_chips = "".join(
        f'<div class="lang" title="{html.escape(lang)}: {n} tickets"><span>{LANG_SCRIPTS.get(lang, lang[:2])}</span>{html.escape(lang)}<b>{n}</b></div>'
        for lang, n in languages.items()
    )
    right.markdown(
        '<div class="info-card"><div class="dash-title" style="margin-top:0">Urgency mix</div>'
        f'<div class="seg-bar">{segments}</div><div class="legend">{legend}</div>'
        '<div class="dash-title">Languages</div>'
        f'<div class="langs">{lang_chips}</div></div>',
        unsafe_allow_html=True,
    )

    # Mood and escalation reasons as ranked infographic bars.
    c1, c2 = st.columns(2, gap="medium")
    moods = df["sentiment"].value_counts().reindex([m for m in MOOD_ICONS if m in set(df["sentiment"])], fill_value=0)
    mood_rows = "".join(
        bar_row(m, int(n), total, MOOD_ICONS[m], SENTIMENT_COLORS.get(m, BLUE), i * 0.08) for i, (m, n) in enumerate(moods.items())
    )
    c1.markdown(f'<div class="info-card"><div class="dash-title" style="margin-top:0">Customer mood</div>{mood_rows}</div>',
                unsafe_allow_html=True)
    reasons = df.loc[df["escalation_reason"] != "", "escalation_reason"].str.split(r" \+ ").explode().str.strip()
    reason_counts = reasons.value_counts().head(5)
    if reason_counts.empty:
        body = '<div class="empty">No escalations yet. Every ticket so far was resolved by AI.</div>'
    else:
        body = "".join(bar_row(r, int(n), escalated, "⚠", ORANGE, i * 0.08) for i, (r, n) in enumerate(reason_counts.items()))
    c2.markdown(f'<div class="info-card"><div class="dash-title" style="margin-top:0">Why tickets went to a human</div>{body}</div>',
                unsafe_allow_html=True)


def render_sidebar(user: dict) -> None:
    with st.sidebar:
        logout_button(user)
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




def render_ticket_status() -> None:
    df = load_log()
    if df.empty:
        st.markdown('<div class="empty">No tickets yet.</div>', unsafe_allow_html=True)
        return
    escalated = df["status"] == "Escalated"
    waiting = df["review_status"] == PENDING
    closed = df["review_status"].str.startswith("Rejected")
    approved = escalated & ~waiting & ~closed
    st.markdown(
        '<div class="kpis">'
        + kpi_card("🤖", "Answered by AI", str(int((~escalated).sum())), "sent straight to the customer")
        + kpi_card("⏳", "Waiting for approval", str(int(waiting.sum())), "open the Approvals tab")
        + kpi_card("✅", "Approved by staff", str(int(approved.sum())), "approved or edited replies")
        + kpi_card("🚫", "Closed", str(int(closed.sum())), "rejected with a note")
        + "</div>",
        unsafe_allow_html=True,
    )
    stage = pd.Series("Answered by AI", index=df.index)
    stage[waiting] = "Waiting for approval"
    stage[approved] = "Approved by staff"
    stage[closed] = "Closed"
    view = df.assign(stage=stage)
    c1, c2 = st.columns([1, 2])
    pick = c1.selectbox("Show", ["All tickets", "Waiting for approval", "Answered by AI", "Approved by staff", "Closed"])
    search = c2.text_input("Search by ticket, customer or order", placeholder="e.g. TKT-0012, priya, ORD-4512")
    if pick != "All tickets":
        view = view[view["stage"] == pick]
    if search:
        hay = view[["ticket_id", "customer_name", "customer_id", "order_id"]].agg(" ".join, axis=1)
        view = view[hay.str.contains(search, case=False, regex=False)]
    c3, c4 = st.columns([3, 1], vertical_alignment="bottom")
    c3.caption(f"{len(view)} of {len(df)} tickets · newest first")
    layout = c4.segmented_control("View", ["Cards", "Table"], default="Cards", key="ts_view", label_visibility="collapsed")
    view = view.iloc[::-1]
    if view.empty:
        st.markdown('<div class="empty">No tickets match these filters.</div>', unsafe_allow_html=True)
        return
    if layout == "Table":
        st.dataframe(
            view[["ticket_id", "timestamp", "customer_name", "customer_id", "order_id", "category", "urgency", "language", "stage", "escalation_reason"]],
            hide_index=True,
            width="stretch",
            column_config={"stage": st.column_config.TextColumn("status"), "customer_id": st.column_config.TextColumn("username")},
        )
        return
    shown = st.session_state.get("ts_shown", TICKETS_PER_PAGE)
    st.markdown('<div class="tk-grid">' + "".join(ticket_card(row) for _, row in view.head(shown).iterrows()) + "</div>",
                unsafe_allow_html=True)
    if len(view) > shown:
        st.button(f"Show more ({len(view) - shown} left)", key="ts_more",
                  on_click=lambda: st.session_state.update(ts_shown=shown + TICKETS_PER_PAGE))


TICKETS_PER_PAGE = 12
STAGE_STYLES = {
    "Answered by AI": ("answered", "🤖"),
    "Waiting for approval": ("waiting", "⏳"),
    "Approved by staff": ("approved", "✅"),
    "Closed": ("closed", "🚫"),
}


def ticket_card(row: pd.Series) -> str:
    """One ticket as a store-style card: status colour strip, who and what, and the reply on demand."""
    e = lambda v: html.escape(str(v or ""))
    cls, icon = STAGE_STYLES[row["stage"]]
    when = pd.to_datetime(row["timestamp"], errors="coerce")
    when = when.strftime("%d %b %Y, %I:%M %p") if pd.notna(when) else row["timestamp"]
    urgency = row["urgency"] or "-"
    chips = (
        f'<span class="tk-chip urg-{e(urgency.lower())}">⚡ {e(urgency)}</span>'
        + (f'<span class="tk-chip">{MOOD_ICONS.get(row["sentiment"], "🙂")} {e(row["sentiment"])}</span>' if row["sentiment"] else "")
        + (f'<span class="tk-chip">{LANG_SCRIPTS.get(row["language"], "🌐")} {e(row["language"])}</span>' if row["language"] else "")
        + (f'<span class="tk-chip">↩ follow-up of {e(row["parent_ticket"])}</span>' if row["parent_ticket"] else "")
    )
    who = f'<span>👤 <b>{e(row["customer_name"]) or "Guest"}</b>' + (f' <small>@{e(row["customer_id"])}</small>' if row["customer_id"] else "") + "</span>"
    order = f'<span>📦 {e(row["order_id"])}</span>' if row["order_id"] else ""
    reason = f'<div class="tk-reason">⚠ {e(row["escalation_reason"])}</div>' if row["escalation_reason"] and cls != "answered" else ""
    reply = row["final_response"] or row["response"]
    reply_label = "Reply sent" if cls in ("answered", "approved") else ("Draft reply" if cls == "waiting" else "Closing note")
    details = (
        f'<details><summary>{reply_label}</summary><div class="tk-reply">{e(reply).replace(chr(10), "<br>")}</div>'
        + (f'<div class="tk-by">Reviewed by {e(row["reviewer"])} · {e(row["reviewed_at"][:16])}</div>' if row["reviewer"] else "")
        + "</details>"
        if reply else ""
    )
    return (
        f'<div class="tk-card tk-{cls}">'
        f'<div class="tk-head"><div><span class="tk-id">{e(row["ticket_id"])}</span>'
        f'<span class="tk-cat">{CATEGORY_ICONS.get(row["category"], "❓")} {e(row["category"] or "Other")}</span></div>'
        f'<span class="tk-status">{icon} {e(row["stage"])}</span></div>'
        f'<div class="tk-when">🕒 {e(when)}</div>'
        f'<div class="tk-text">{e(row["followup_text"] or row["complaint"])}</div>'
        f'<div class="tk-who">{who}{order}</div>'
        f'<div class="tk-chips">{chips}</div>{reason}{details}</div>'
    )


def render_users() -> None:
    users = pd.DataFrame(auth.list_users())
    st.markdown('<div class="section-title">Accounts</div>', unsafe_allow_html=True)
    st.dataframe(users[["username", "name", "role", "email", "created"]], hide_index=True, width="stretch")

    c1, c2 = st.columns(2, gap="medium")
    with c1, st.form("new_user", clear_on_submit=True):
        st.markdown(f"**Create a user**  \nNew accounts get the default password **{auth.DEFAULT_PASSWORD}**.")
        username = st.text_input("Username", placeholder="e.g. suresh")
        name = st.text_input("Full name")
        email = st.text_input("Email (optional)")
        role = st.selectbox("Role", ["customer", "admin"])
        if st.form_submit_button("Create user"):
            try:
                auth.create_user(username, name, role, email)
                st.session_state["users_msg"] = f"Created '{username.strip().lower()}' with the password {auth.DEFAULT_PASSWORD}."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with c2, st.container(border=True):
        st.markdown(f"**Reset a password**  \nSets it back to **{auth.DEFAULT_PASSWORD}**.")
        who = st.selectbox("User", [u for u in users["username"] if u != auth.ADMIN_USERNAME])
        if st.button("Reset password"):
            auth.reset_password(who)
            st.session_state["users_msg"] = f"The password for '{who}' is now {auth.DEFAULT_PASSWORD}."
            st.rerun()
    if msg := st.session_state.pop("users_msg", None):
        st.success(msg)


def render_knowledge() -> None:
    """Every knowledge-base section with its metadata, filters, and a search test that shows how
    the vector and keyword rankings were fused."""
    sections = pd.DataFrame(load_sections())
    c1, c2 = st.columns(2)
    topics = c1.multiselect("Topic", [t for t in TOPICS if t in set(sections["topic"])])
    docs = c2.multiselect("Document", sorted(sections["doc_title"].unique()))
    view = sections
    if topics:
        view = view[view["topic"].isin(topics)]
    if docs:
        view = view[view["doc_title"].isin(docs)]
    st.caption(f"{len(view)} of {len(sections)} sections")
    st.dataframe(
        view.assign(words=view["text"].str.split().str.len())[["topic", "doc_title", "heading", "source", "words"]],
        hide_index=True,
        width="stretch",
        column_config={"doc_title": "document", "heading": "section"},
    )

    st.markdown('<div class="section-title">Try a search</div>', unsafe_allow_html=True)
    q1, q2 = st.columns([3, 1])
    query = q1.text_input("Question", placeholder="e.g. how long is the reset code valid")
    topic = q2.selectbox("Category boost", ["(none)"] + TOPICS)
    if not query.strip():
        return
    cols = st.columns(3)
    for col, method, title in zip(cols, ["dense", "bm25", "hybrid"], ["Vector only (ChromaDB)", "Keyword only (BM25)", "Hybrid (used by the agent)"]):
        hits, _ = search_passages(query, topic="" if topic == "(none)" else topic, method=method)
        rows = "".join(
            f"<li><b>{html.escape(h['heading'])}</b><br><small>{html.escape(h['source'])} · {h['topic']}"
            + (f" · vector #{h['dense_rank']}" if h["dense_rank"] else "")
            + (f" · keyword #{h['bm25_rank']}" if h["bm25_rank"] else "")
            + "</small></li>"
            for h in hits
        ) or "<li>No relevant section</li>"
        col.markdown(f'<div class="card"><b>{title}</b><ol style="margin:0.6rem 0 0 1.1rem;padding:0">{rows}</ol></div>', unsafe_allow_html=True)


def agent_strip() -> str:
    """The support team as a row of round icons, like a store's category strip."""
    captions = ["Reads the complaint", "Finds the policy", "Writes the reply", "Records & escalates"]
    steps = [(AGENT_ICONS[a], AGENT_LABELS[a].replace(" Agent", ""), c) for a, c in zip(AGENT_STEPS, captions)]
    steps.append(("👤", "Human review", "Approves hard cases"))
    return '<div class="fk-cats">' + '<span class="fk-arrow">›</span>'.join(
        f'<div class="fk-cat"><div class="ic">{icon}</div><b>{html.escape(name)}</b><small>{html.escape(caption)}</small></div>'
        for icon, name, caption in steps
    ) + "</div>"


def render_admin_search(query: str) -> None:
    """Header search: tickets by ID, customer, order, category or complaint text, plus matching users."""
    df = load_log()
    q = query.lower()
    cols = ["ticket_id", "customer_name", "customer_id", "order_id", "category", "status", "review_status", "complaint"]
    hits = df[df[cols].apply(lambda r: q in " ".join(r).lower(), axis=1)] if not df.empty else df
    users = [u for u in auth.list_users() if q in f'{u["username"]} {u["name"]}'.lower()]
    with st.container(border=True):
        st.markdown(f'<div class="section-title" style="margin-top:0">Search results for “{html.escape(query)}”</div>'
                    f'<div class="foot">{len(hits)} tickets · {len(users)} users</div>', unsafe_allow_html=True)
        if not hits.empty:
            st.dataframe(hits.iloc[::-1][cols], hide_index=True, width="stretch",
                         column_config={"complaint": st.column_config.TextColumn("complaint", width="large")})
        if users:
            st.dataframe(pd.DataFrame(users)[["username", "name", "role"]], hide_index=True, width="stretch")
        if hits.empty and not users:
            st.markdown('<div class="empty">No tickets or users match that.</div>', unsafe_allow_html=True)
        if st.button("Clear search", key="adm_clear", on_click=lambda: st.session_state.update(adm_search="")):
            pass


def render_admin(user: dict) -> None:
    render_sidebar(user)
    with st.container(key="fk_header"):
        logo, search, who = st.columns([1.25, 4.8, 1.6], vertical_alignment="center")
        logo.markdown('<div class="fk-logo">ShopNest<small>Support <i>✦</i> AI Desk</small></div>', unsafe_allow_html=True)
        query = search.text_input("Search", key="adm_search", placeholder="Search tickets, customers and orders",
                                  label_visibility="collapsed", icon=":material/search:")
        who.markdown(f'<div class="fk-links"><span class="pill">{html.escape(user["name"])}</span></div>', unsafe_allow_html=True)
    if query.strip():
        render_admin_search(query.strip())
    st.markdown(agent_strip(), unsafe_allow_html=True)
    # Fixed labels: a label that changes (like a live count) would make Streamlit jump back to the first tab.
    tabs = st.tabs(["Dashboard", "Ticket status", "Approvals", "Knowledge base", "Users", "Ticket log", "Agent console"])
    with tabs[0]:
        render_dashboard()
    with tabs[1]:
        render_ticket_status()
    with tabs[2]:
        render_approvals()
    with tabs[3]:
        render_knowledge()
    with tabs[4]:
        render_users()
    with tabs[5]:
        render_log()
    with tabs[6]:
        st.markdown(
            '<div class="help-box">Test the agents directly: run any complaint and watch each agent\'s output. '
            "Customers raise tickets from their orders in the customer portal.</div>",
            unsafe_allow_html=True,
        )
        render_console()
