"""Customer portal: My Orders (filters, search, status, raise a complaint), My Tickets and My Account."""

import asyncio
import html
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import auth
from agents.knowledge_agent import TOPICS, load_sections, search_passages
from orders import STATUSES, order_summary, orders_for
from team import AGENT_LABELS
from ui.common import (
    AGENT_ICONS,
    AGENT_STEPS,
    as_paragraphs,
    customer_status,
    load_log,
    logout_button,
    process_followup,
    pipeline_html,
    process_ticket,
)
from wishlist import add_item, get_wishlist, remove_item

# What the customer sees while each agent works.
FRIENDLY_STEPS = {
    "query_agent": "Understood your request",
    "knowledge_agent": "Checked ShopNest policies",
    "resolution_agent": "Wrote your reply",
    "log_agent": "Saved your ticket",
}
WAITING_STEPS = {
    "query_agent": "Understanding your request...",
    "knowledge_agent": "Checking ShopNest policies...",
    "resolution_agent": "Writing your reply...",
    "log_agent": "Saving your ticket...",
}
LANGUAGES_HINT = "Write in any language: English, தமிழ், മലയാളം, తెలుగు or हिन्दी."


def _field(content: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def plain(text: str) -> str:
    """Policy markdown as one readable line of text: no **, bullets as •, table rows as 'a · b'."""
    lines = []
    for line in text.replace("**", "").splitlines():
        line = line.strip()
        if re.fullmatch(r"\|?[\s:|-]+\|?", line):
            continue  # table separator row
        if line.startswith("|"):
            line = " · ".join(c.strip() for c in line.strip("|").split("|"))
        elif line.startswith("- "):
            line = "• " + line[2:]
        if line:
            lines.append(line)
    return "  ".join(lines)


def chips(*items: tuple[str, str]) -> str:
    """Badges: items are (text, css modifier)."""
    shown = [f'<span class="chip {css}">{html.escape(text)}</span>' for text, css in items if text and not text.endswith(": ")]
    return f'<div class="chips">{"".join(shown)}</div>' if shown else ""


def source_chips(sources: str) -> str:
    names = [s.strip() for s in re.split(r"[,;]", sources or "") if s.strip() and s.strip().upper() != "NONE"]
    if not names:
        return ""
    return chips(*[(f"📄 {n}", "src") for n in names])


AGENT_TAGLINES = {
    "query_agent": "Understands the complaint",
    "knowledge_agent": "Searches ShopNest policies",
    "resolution_agent": "Writes the reply",
    "log_agent": "Logs and routes the ticket",
}
CATEGORY_ICON = {"Shipping": "🚚", "Refund": "💸", "Account": "👤", "Product": "📦", "Billing": "💳"}
URGENCY_TONE = {"Low": "ok", "Medium": "warn", "High": "bad", "Critical": "bad"}
MOOD_EMOJI = {"Positive": "😊", "Neutral": "😐", "Frustrated": "😕", "Angry": "😠", "Very Angry": "😡"}
HELD_LIVE = "Draft ready. It appears once the Log Agent has checked the escalation rules."
HELD_REVIEW = "Draft held until a support specialist approves it."


def _e(text: str) -> str:
    return html.escape(text or "")


def _tile(icon: str, label: str, value: str, tone: str = "") -> str:
    return f'<div class="ao-tile {tone}"><span class="ao-ic">{icon}</span><div><small>{_e(label)}</small><b>{_e(value or "-")}</b></div></div>'


def _short(text: str, limit: int) -> str:
    text = plain(text).replace("• ", "").replace("  ", " ")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def agent_body(source: str, content: str, held: str = "") -> str:
    """Short, structured view of one agent's output (the full message stays one click away)."""
    if source == "query_agent":
        urgency, mood = _field(content, "URGENCY"), _field(content, "SENTIMENT")
        summary = _field(content, "SUMMARY")
        return (
            '<div class="ao-tiles">'
            + _tile(CATEGORY_ICON.get(_field(content, "CATEGORY"), "🏷️"), "Category", _field(content, "CATEGORY"))
            + _tile("⚡", "Urgency", urgency, URGENCY_TONE.get(urgency, ""))
            + _tile(MOOD_EMOJI.get(mood, "🙂"), "Mood", mood)
            + _tile("🌐", "Language", _field(content, "LANGUAGE") or "English")
            + "</div>"
            + (f'<div class="ao-quote">“{_e(summary)}”</div>' if summary else "")
        )
    if source == "knowledge_agent":
        hits = re.findall(r"^\[(\d+)\] (\S+) > (.+?) \(topic: ([^;]+); found by ([^)]*)\)\n(.+?)(?=^\[\d+\] |\Z)", content, re.MULTILINE | re.DOTALL)
        if not hits:
            return '<div class="ao-empty">🔎 No policy covers this exactly, so a support specialist will check it.</div>'
        rows = []
        for rank, doc, heading, topic, found_by, text in hits:
            pills = "".join(f'<span class="ao-pill {w.strip()}">{_e(w.strip())}</span>' for w in found_by.split("+"))
            rows.append(
                f'<div class="ao-hit"><span class="ao-rank">{rank}</span><div class="ao-hit-body">'
                f'<div class="ao-hit-title">{_e(heading)} <span class="ao-doc">· {_e(doc)}</span></div>'
                f'<div class="ao-hit-text">{_e(_short(text.strip().split(chr(10), 1)[-1], 130))}</div></div>'
                f'<div class="ao-hit-meta"><span class="ao-pill topic">{_e(topic)}</span>{pills}</div></div>'
            )
        return f'<div class="ao-sub">{len(hits)} passages found · hybrid search (vector + keyword)</div>' + "".join(rows)
    if source == "resolution_agent":
        confidence = _field(content, "CONFIDENCE")
        level = {"High": 3, "Medium": 2, "Low": 1}.get(confidence, 0)
        meter = "".join(f'<i class="{"on" if i < level else ""}"></i>' for i in range(3))
        reply = re.search(r"REPLY:\s*(.*?)\s*(?:^USED_SOURCES:|^CONFIDENCE:|\Z)", content, re.DOTALL | re.MULTILINE)
        preview = f'🔒 {held}' if held else _short(reply.group(1) if reply else content, 220)
        return (
            f'<div class="ao-reply{" held" if held else ""}">{_e(preview)}</div>'
            f'<div class="ao-row"><div class="ao-meter" title="Confidence: {_e(confidence)}"><span>Confidence</span>{meter}<b>{_e(confidence or "-")}</b></div>'
            f'{source_chips(_field(content, "USED_SOURCES"))}</div>'
        )
    match = re.search(r"LOGGED (\S+) \| status: (\w+)(?: \| reason: (.+))?", content)
    if not match:
        return '<div class="ao-empty">Ticket saved.</div>'
    ticket, status, reason = match.group(1), match.group(2), (match.group(3) or "").strip()
    ok = status == "Resolved"
    reasons = "".join(f'<span class="ao-pill bad">{_e(r.strip())}</span>' for r in reason.split("+") if r.strip())
    return (
        f'<div class="ao-log"><div class="ao-ticket"><small>Ticket</small><b>{_e(ticket)}</b></div>'
        f'<div class="ao-status {"ok" if ok else "bad"}">{"✓ Resolved by AI" if ok else "⚠ Escalated to a specialist"}</div>'
        f'<div class="ao-reasons">{reasons}</div></div>'
    )


def agent_card(number: int, source: str, content: str, held: str = "") -> str:
    """A rich card for one AutoGen agent's step, with its raw message tucked into a details toggle."""
    raw = content
    if held and source == "resolution_agent":  # never show the unapproved draft, even in the raw view
        raw = "\n".join(line for line in content.splitlines() if line.startswith(("USED_SOURCES:", "CONFIDENCE:")))
        raw = f"REPLY: ({held})\n{raw}"
    raw_html = _e(raw.strip()).replace("\n", "<br>")
    return (
        f'<div class="ao-card {source}"><div class="ao-head"><div class="ao-icon">{AGENT_ICONS[source]}</div>'
        f'<div class="ao-title"><small>Step {number} · {_e(AGENT_TAGLINES[source])}</small><b>{_e(AGENT_LABELS[source])}</b></div>'
        f'<div class="ao-done">✓ Done</div></div>'
        f'<div class="ao-body">{agent_body(source, content, held)}</div>'
        f'<details class="ao-raw"><summary>View raw AutoGen message</summary><div>{raw_html}</div></details></div>'
    )


def render_step(number: int, source: str, content: str, expanded: bool = True, held: str = "") -> None:
    st.markdown(agent_card(number, source, content, held), unsafe_allow_html=True)


def live_timeline(title: str):
    """Show the four steps as waiting rows; return (on_step, slots); on_step turns a row into the agent's step."""
    st.markdown(f'<div class="section-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    flow = st.empty()
    flow.markdown(pipeline_html(set(), "query_agent"), unsafe_allow_html=True)
    finished = set()
    slots = {src: st.empty() for src in AGENT_STEPS}
    for src in AGENT_STEPS:
        slots[src].markdown(
            f'<div class="ao-card wait"><div class="ao-head"><div class="ao-icon">{AGENT_ICONS[src]}</div>'
            f'<div class="ao-title"><small>{html.escape(WAITING_STEPS[src])}</small><b>{html.escape(AGENT_LABELS[src])}</b></div>'
            f'<div class="ao-wait">Waiting</div></div></div>',
            unsafe_allow_html=True,
        )

    def on_step(number: int, source: str, content: str) -> None:
        finished.add(source)
        nxt = next((a for a in AGENT_STEPS if a not in finished), None)
        flow.markdown(pipeline_html(finished, nxt), unsafe_allow_html=True)
        with slots[source].container():
            # The draft stays hidden until the Log Agent decides; the completed view shows it if no review is needed.
            render_step(number, source, content, held=HELD_LIVE)

    return on_step, slots


def my_tickets(user: dict) -> pd.DataFrame:
    """This customer's tickets; tickets from before the portal are matched by first name."""
    df = load_log()
    first = user["name"].split()[0].lower()
    mine = (df["customer_id"] == user["username"]) | ((df["customer_id"] == "") & (df["customer_name"].str.lower() == first))
    return df[mine].iloc[::-1]


def order_card(order: dict, ticket) -> str:
    chip = ""
    if ticket is not None:
        label, css, _ = customer_status(ticket)
        kind = "wait" if css == "ts-review" else "done"
        chip = f'<span class="tchip {kind}">Ticket {html.escape(ticket["ticket_id"])} · {label}</span>'
    return (
        f'<div class="order"><div class="pic">{order["icon"]}</div>'
        f'<div class="prod"><b>{html.escape(order["product"])}</b><small>{html.escape(order["variant"])} · {order["order_id"]}</small><br>{chip}</div>'
        f'<div class="price">₹{order["price"]:,}</div>'
        f'<div class="stat"><b><span class="tone tone-{order["tone"]}"></span>{html.escape(order["headline"])}</b>'
        f'<small>{html.escape(order["note"])}</small></div></div>'
    )


def _in_period(ordered: date, periods: list[str], today: date) -> bool:
    if not periods:
        return True
    checks = {
        "Last 30 days": ordered >= today - timedelta(days=30),
        str(today.year): ordered.year == today.year,
        str(today.year - 1): ordered.year == today.year - 1,
        "Older": ordered.year < today.year - 1,
    }
    return any(checks[p] for p in periods)


def reply_card(user: dict, outcome) -> str:
    if outcome.status == "Resolved":
        return (
            f'<div class="card"><span class="ticket-status ts-answered">Answered</span>'
            f'<div class="foot" style="margin:0.4rem 0 0.8rem">Ticket {html.escape(outcome.ticket_id)} · Reply from ShopNest Support</div>'
            f'<div class="reply">{as_paragraphs(outcome.reply)}</div>'
            f'<div class="foot" style="margin-top:0.6rem">Based on our policies:</div>{source_chips(outcome.used_sources)}</div>'
        )
    return (
        f'<div class="card"><span class="ticket-status ts-review">Under review</span>'
        f'<div class="reply" style="margin-top:0.8rem"><p>Thank you, {html.escape(user["name"].split()[0])}. '
        f"A ShopNest support specialist is reviewing your request (ticket {html.escape(outcome.ticket_id)}). "
        "You'll see our reply in <b>My Tickets</b> as soon as it is approved.</p></div></div>"
    )


def render_help_done(user: dict, done: dict) -> None:
    """The completed request: what was sent, every agent's step, and the reply. No editable form any more."""
    outcome = done["outcome"]
    held = HELD_REVIEW if outcome.status != "Resolved" else ""
    st.markdown(
        f'<div class="done-box"><span class="ic">✓</span><div><b>Ticket {html.escape(outcome.ticket_id)} logged</b>'
        f'<small>{"Answered by our AI assistant" if not held else "Sent to a support specialist for review"}</small></div></div>'
        f'<div class="complaint" style="margin-top:0.6rem"><b>You wrote:</b> {html.escape(done["complaint"])}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-title">How we handled your request</div>', unsafe_allow_html=True)
    verdict = "sent to a support specialist for review" if held else "answered by AI"
    st.markdown(pipeline_html(set(AGENT_STEPS), None, f"Ticket {outcome.ticket_id} · all 4 agents finished · {verdict}", finished=True),
                unsafe_allow_html=True)
    for number, (source, content) in enumerate(outcome.steps, start=1):
        render_step(number, source, content, expanded=True, held=held)
    st.markdown('<div class="section-title">Our reply</div>', unsafe_allow_html=True)
    st.markdown(reply_card(user, outcome), unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.9, 1.7, 2.6])
    if c1.button("Raise another request", key="help_again", type="primary"):
        st.session_state.pop("help_done", None)
        st.rerun()
    if c2.button("View in My Tickets", key="help_tickets"):
        st.session_state.pop("help_done", None)
        st.session_state.pop("help_order", None)
        st.session_state["page"] = "My Tickets"
        st.rerun()


def render_help(user: dict) -> None:
    """Raise a complaint about one order (or a general one) and run the agent team."""
    order = st.session_state["help_order"]
    with st.container(border=True):
        if order:
            st.markdown(
                f'<div class="section-title" style="margin-top:0">Help with your order</div>{order_card(order, None)}',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="section-title" style="margin-top:0">Help with something else</div>'
                        '<div class="help-box">Account and login, payments, gift cards or any other question.</div>', unsafe_allow_html=True)
        if done := st.session_state.get("help_done"):
            render_help_done(user, done)
            return
        with st.form("complaint", border=False):
            text = st.text_area("Describe your issue", height=110, placeholder=LANGUAGES_HINT, help=LANGUAGES_HINT)
            c1, c2, _ = st.columns([1, 1, 3])
            send = c1.form_submit_button("Submit")
            back = c2.form_submit_button("Cancel")  # styled white via .st-key-FormSubmitter-complaint-Cancel
        if back:
            st.session_state.pop("help_order", None)
            st.rerun()
        if not send:
            return
        if not text.strip():
            st.warning("Please describe your issue first.")
            return
        on_step, slots = live_timeline("How we're handling your request")
        try:
            outcome = asyncio.run(
                process_ticket(
                    text,
                    user["name"].split()[0],
                    order["order_id"] if order else "",
                    on_step,
                    order_details=order_summary(order) if order else "",
                    customer_id=user["username"],
                )
            )
        except Exception as exc:  # show API/config problems instead of a stack trace
            st.error(f"Sorry, we couldn't process your request right now: {exc}")
            return
        if outcome is None or not outcome.ticket_id:
            st.error("Sorry, your request could not be saved. Please try again.")
            return
        # Ticket logged: switch to the completed view (the form is replaced, the steps stay visible).
        st.session_state["help_done"] = {"complaint": text.strip(), "outcome": outcome}
        st.rerun()


def render_orders(user: dict) -> None:
    st.markdown('<div class="crumb">Home › My Account › My Orders</div>', unsafe_allow_html=True)
    if "help_order" in st.session_state:
        render_help(user)
        if st.button("← Back to my orders"):
            st.session_state.pop("help_order", None)
            st.session_state.pop("help_done", None)
            st.rerun()
        return

    orders = orders_for(user["username"])
    tickets = my_tickets(user)
    latest = {}  # newest ticket for each order
    for _, row in tickets.iloc[::-1].iterrows():
        if row["order_id"]:
            latest[row["order_id"]] = row
    today = date.today()

    left, right = st.columns([1, 3.4], gap="medium")
    with left, st.container(border=True):
        st.markdown('<div class="filter-title">Filters</div><div class="filter-label">Order status</div>', unsafe_allow_html=True)
        statuses = [s for s in STATUSES if st.checkbox(s, key=f"f_{s}")]
        st.markdown('<div class="filter-label">Order time</div>', unsafe_allow_html=True)
        periods = [p for p in ["Last 30 days", str(today.year), str(today.year - 1), "Older"] if st.checkbox(p, key=f"t_{p}")]

    with right:
        c1, c2 = st.columns([4.2, 1.6])
        search = c1.text_input("Search your orders", placeholder="Search your orders here", label_visibility="collapsed")
        c2.button("Search Orders", type="primary", width="stretch")
        shown = [
            o for o in orders
            if (not statuses or o["status"] in statuses)
            and _in_period(o["ordered_on"], periods, today)
            and (not search or search.lower() in f'{o["product"]} {o["order_id"]} {o["variant"]}'.lower())
        ]
        if not shown:
            st.markdown('<div class="empty">No orders match these filters.</div>', unsafe_allow_html=True)
        for order in shown:
            with st.container(border=True):
                st.markdown(order_card(order, latest.get(order["order_id"])), unsafe_allow_html=True)
                _, w, b = st.columns([3.7, 1.3, 1.3])
                if w.button("♡ Wishlist", key=f"wish_{order['order_id']}", width="stretch"):
                    item = {**order, "id": order["order_id"]}
                    st.toast("Added to your wishlist" if add_item(user["username"], item) else "Already in your wishlist")
                if b.button("Need help?", key=f"help_{order['order_id']}", width="stretch"):
                    st.session_state["help_order"] = order
                    st.rerun()
        st.markdown('<div class="help-box" style="margin-top:0.8rem">Question about your account, a payment or a gift card?</div>', unsafe_allow_html=True)
        if st.button("Get help with something else"):
            st.session_state["help_order"] = None
            st.rerun()


def render_followup(user: dict, row) -> None:
    """Let the customer reply on an answered ticket; the reply becomes a new, linked ticket."""
    tid = row["ticket_id"]
    with st.expander("Still need help? Reply to this ticket"):
        with st.form(f"followup_{tid}", border=False):
            text = st.text_area("Your reply", key=f"fu_text_{tid}", height=90, placeholder=LANGUAGES_HINT)
            send = st.form_submit_button("Send reply")
        if not send:
            return
        if not text.strip():
            st.warning("Please write your reply first.")
            return
        on_step, _ = live_timeline("How we're handling your reply")
        try:
            standalone, outcome = asyncio.run(process_followup(row, text, user["name"].split()[0], user["username"], on_step))
        except Exception as exc:  # show API/config problems instead of a stack trace
            st.error(f"Sorry, we couldn't process your reply right now: {exc}")
            return
        if outcome is None or not outcome.ticket_id:
            st.error("Sorry, your reply could not be saved. Please try again.")
            return
        st.session_state["fu_done"] = outcome.ticket_id
        st.success(f"Thanks, your reply was sent as ticket {outcome.ticket_id}.")
        st.button("Show it in My Tickets", key=f"fu_show_{tid}")  # any click reruns and refreshes the list


def render_my_tickets(user: dict) -> None:
    tickets = my_tickets(user)
    if done := st.session_state.pop("fu_done", None):
        st.success(f"Your reply was sent as ticket {done}. It's at the top of this list.")
    if tickets.empty:
        st.markdown('<div class="empty">You have no tickets yet. Use <b>Need help?</b> on any order.</div>', unsafe_allow_html=True)
        return
    render_ticket_log(tickets)
    for _, row in tickets.iterrows():
        label, css, reply = customer_status(row)
        if css == "ts-review":
            body = "<p>A ShopNest support specialist is reviewing your request. We'll reply here soon.</p>"
        elif css == "ts-closed":
            body = "<p>Our support team has reviewed this request and will contact you directly.</p>"
        else:
            body = as_paragraphs(reply)
        order = f" · {html.escape(row['order_id'])}" if row["order_id"] else ""
        parent = f" · follow-up to {html.escape(row['parent_ticket'])}" if row["parent_ticket"] else ""
        st.markdown(
            f'<div class="card" style="margin-bottom:0.3rem"><div class="review-head"><b>{html.escape(row["ticket_id"])}{order}</b>'
            f'<span class="ticket-status {css}">{label}</span></div>'
            f'<div class="foot" style="margin-top:0.2rem">Raised on {html.escape(row["timestamp"][:16])} · {html.escape(row["category"] or "-")}{parent}</div>'
            f'{chips((row["category"], ""), (row["language"], ""))}'
            f'<div class="complaint"><b>You wrote:</b> {html.escape(row["followup_text"] or row["complaint"])}</div>'
            f'<div class="reply" style="margin-top:0.6rem">{body}</div>'
            f'{source_chips(row["kb_sources"]) if css == "ts-answered" else ""}</div>',
            unsafe_allow_html=True,
        )
        render_ticket_steps(row, css)
        if css != "ts-review":
            render_followup(user, row)
        st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)


CUSTOMER_STATUS = {"ts-answered": "Answered", "ts-review": "Under review", "ts-closed": "Closed"}


def render_ticket_log(tickets: pd.DataFrame) -> None:
    """A table of all this customer's tickets, with a CSV download."""
    rows = []
    for _, row in tickets.iterrows():
        label, _, _ = customer_status(row)
        rows.append(
            {
                "Ticket": row["ticket_id"],
                "Raised on": row["timestamp"][:16],
                "Order": row["order_id"],
                "Category": row["category"],
                "Language": row["language"],
                "Status": label,
                "Sources": row["kb_sources"] if label == "Answered" else "",
                "You wrote": row["followup_text"] or row["complaint"],
            }
        )
    table = pd.DataFrame(rows)
    counts = table["Status"].value_counts()
    with st.expander(
        f"📋 My ticket log · {len(table)} tickets · {counts.get('Answered', 0)} answered · {counts.get('Under review', 0)} under review"
    ):
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button("Download CSV", table.to_csv(index=False).encode("utf-8"), "my_tickets.csv", "text/csv")


def render_ticket_steps(row, css: str) -> None:
    """How each agent handled this ticket, from the ticket log."""
    with st.expander("How we handled this ticket"):
        urgency = row["urgency"]
        steps = [
            ("query_agent", chips((f"Category: {row['category']}", ""), (f"Urgency: {urgency}", "high" if urgency.lower() in ("high", "critical") else ""),
                                  (f"Mood: {row['sentiment']}", ""), (f"Language: {row['language'] or 'English'}", ""))),
            ("knowledge_agent", source_chips(row["kb_sources"]) or '<div class="kb-doc">No matching policy found.</div>'),
            ("resolution_agent", chips((f"Confidence: {row['confidence']}", "ok" if row["confidence"] == "High" else ""))),
            ("log_agent", chips((CUSTOMER_STATUS[css], "ok" if css == "ts-answered" else "high"),
                                ("Checked by a specialist", "") if row["reviewer"] else ("", ""))),
        ]
        for source, body in steps:
            st.markdown(f"**{AGENT_ICONS[source]} {FRIENDLY_STEPS[source]}**")
            st.markdown(body, unsafe_allow_html=True)


def render_help_centre() -> None:
    """Browse and search the policy documents the AI answers from."""
    st.markdown(
        '<div class="help-box">Our AI assistant answers only from these ShopNest policy documents, and every reply shows which document it used.</div>',
        unsafe_allow_html=True,
    )
    query = st.text_input("Search our policies", placeholder="e.g. how long does a refund take", key="hc_search")
    if query.strip():
        hits, _ = search_passages(query)
        if not hits:
            st.markdown('<div class="empty">Nothing in our policies matches that. Raise a ticket and a specialist will help.</div>', unsafe_allow_html=True)
        for hit in hits:
            with st.container(border=True):
                st.markdown(f'<div class="kb-hit" style="margin:0"><b>📄 {html.escape(hit["source"])} › {html.escape(hit["heading"])} · {html.escape(hit["topic"])}</b></div>',
                            unsafe_allow_html=True)
                st.markdown(hit["text"].split("\n", 1)[-1])  # the policy's own markdown (bullets, tables)
    sections = load_sections()
    docs = {}
    for sec in sections:
        docs.setdefault((sec["source"], sec["doc_title"]), []).append(sec)
    cols = st.columns(2, gap="medium")
    for i, ((source, title), secs) in enumerate(docs.items()):
        topics = sorted({s["topic"] for s in secs}, key=TOPICS.index)
        with cols[i % 2], st.container(border=True):
            st.markdown(
                f'<div class="section-title" style="margin-top:0">📄 {html.escape(title)}</div>'
                f'<div class="kb-doc">{html.escape(source)} · {len(secs)} sections</div>{chips(*[(t, "") for t in topics])}',
                unsafe_allow_html=True,
            )
            for sec in secs:
                with st.expander(sec["heading"]):
                    st.markdown(sec["text"].split("\n", 1)[-1])


def render_account(user: dict) -> None:
    orders = orders_for(user["username"])
    tickets = my_tickets(user)
    st.markdown('<div class="crumb">Home › My Account › My Profile</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True):
        st.markdown(
            f'<div class="profile-head"><div class="avatar">{html.escape(user["name"][:1].upper())}</div>'
            f'<div><small>Hello,</small><b>{html.escape(user["name"])}</b></div></div>'
            f'<div class="section-title">Personal information</div>'
            f'<div class="meta"><span><b>Name</b> {html.escape(user["name"])}</span><span><b>Username</b> {html.escape(user["username"])}</span>'
            f'<span><b>Email</b> {html.escape(user.get("email") or "Not added")}</span>'
            f'<span><b>Member since</b> {html.escape(user.get("created", "")[:10])}</span></div>'
            f'<div class="section-title">Your activity</div>'
            f'<div class="act-row"><div><b>{len(orders)}</b><small>Orders</small></div><div><b>{len(tickets)}</b><small>Tickets</small></div>'
            f'<div><b>{len(get_wishlist(user["username"]))}</b><small>Wishlist</small></div></div>',
            unsafe_allow_html=True,
        )
    with c2, st.form("change_password", clear_on_submit=True):
        st.markdown("**Change password**")
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password", help="At least 8 characters, with letters and a number.")
        again = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Save password"):
            if new != again:
                st.error("The new passwords don't match.")
            elif error := auth.change_password(user["username"], old, new):
                st.error(error)
            else:
                st.success("Your password has been changed.")


PAGES = {  # page -> (material icon, shown in the account menu)
    "My Profile": (":material/account_circle:", True),
    "My Orders": (":material/package_2:", True),
    "My Tickets": (":material/confirmation_number:", False),
    "Wishlist": (":material/favorite:", True),
    "Notifications": (":material/notifications:", True),
    "Help Centre": (":material/help:", False),
}
NAV = ["My Orders", "My Tickets", "Wishlist", "Notifications", "Help Centre", "My Profile"]


def go(page: str) -> None:
    st.session_state["page"] = page
    st.session_state.pop("help_done", None)
    st.session_state["menu_n"] = st.session_state.get("menu_n", 0) + 1  # a new key re-creates the account menu closed
    st.session_state.pop("help_order", None)
    st.rerun()


def notifications(user: dict) -> list[dict]:
    """Updates for this customer, newest first: ticket replies and reviews, and order progress."""
    items = []
    for _, row in my_tickets(user).iterrows():
        label, css, _ = customer_status(row)
        tid = row["ticket_id"]
        if css == "ts-review":
            text, icon = f"Ticket {tid} is with a support specialist. We'll reply soon.", "⏳"
        elif css == "ts-closed":
            text, icon = f"Ticket {tid} was reviewed. Our team will contact you directly.", "📞"
        elif row["reviewer"]:
            text, icon = f"A specialist approved the reply to ticket {tid}.", "✅"
        else:
            text, icon = f"We replied to ticket {tid}.", "💬"
        items.append({"when": row["timestamp"][:16], "icon": icon, "text": text, "page": "My Tickets"})
    for order in orders_for(user["username"]):
        if order["status"] in ("On the way", "Delivered") or (date.today() - order["ordered_on"]).days <= 30:
            items.append(
                {"when": f"{order['ordered_on']:%Y-%m-%d}", "icon": order["icon"],
                 "text": f"{order['product']}: {order['headline']}.", "page": "My Orders"}
            )
    return sorted(items, key=lambda n: n["when"], reverse=True)


def render_notifications(user: dict) -> None:
    st.markdown('<div class="crumb">Home › My Account › Notifications</div>', unsafe_allow_html=True)
    items = notifications(user)
    if not items:
        st.markdown('<div class="empty">No notifications yet.</div>', unsafe_allow_html=True)
    for i, n in enumerate(items):
        with st.container(border=True):
            a, b = st.columns([6, 1.2], vertical_alignment="center")
            a.markdown(f'<div class="notif"><span class="ic">{n["icon"]}</span><div><b>{html.escape(n["text"])}</b>'
                       f'<small>{html.escape(n["when"])}</small></div></div>', unsafe_allow_html=True)
            if b.button("View", key=f"notif_{i}", width="stretch"):
                go(n["page"])


def render_wishlist(user: dict) -> None:
    st.markdown('<div class="crumb">Home › My Account › Wishlist</div>', unsafe_allow_html=True)
    items = get_wishlist(user["username"])
    st.markdown(f'<div class="section-title" style="margin-top:0">My Wishlist ({len(items)})</div>', unsafe_allow_html=True)
    if not items:
        st.markdown('<div class="empty">Your wishlist is empty. Use <b>♡ Wishlist</b> on any order to save it here.</div>', unsafe_allow_html=True)
    for item in items:
        with st.container(border=True):
            a, b = st.columns([6, 1.2], vertical_alignment="center")
            a.markdown(
                f'<div class="order" style="grid-template-columns:72px 1fr 120px"><div class="pic">{item["icon"]}</div>'
                f'<div class="prod"><b>{html.escape(item["product"])}</b><small>{html.escape(item["variant"])}</small></div>'
                f'<div class="price">₹{item["price"]:,}</div></div>',
                unsafe_allow_html=True,
            )
            if b.button("Remove", key=f"unwish_{item['id']}", icon=":material/delete:", width="stretch"):
                remove_item(user["username"], item["id"])
                st.rerun()


def _start_search() -> None:
    """Pressing Enter in the header search opens the results page (or leaves it when the box is cleared)."""
    if st.session_state.get("hdr_search", "").strip():
        st.session_state["page"] = "Search"
    elif st.session_state.get("page") == "Search":
        st.session_state["page"] = "My Orders"
    st.session_state.pop("help_order", None)
    st.session_state.pop("help_done", None)


def render_search(user: dict) -> None:
    """Results for the header search: matching orders, tickets and help articles."""
    query = st.session_state.get("hdr_search", "").strip()
    st.markdown(f'<div class="crumb">Home › Search › “{html.escape(query)}”</div>', unsafe_allow_html=True)
    if not query:
        st.markdown('<div class="empty">Type in the search bar and press Enter.</div>', unsafe_allow_html=True)
        return
    q = query.lower()
    words = [w for w in re.findall(r"\w+", q) if len(w) > 1]

    def matches(text: str) -> bool:
        text = text.lower()
        return q in text or (bool(words) and all(w in text for w in words))

    orders = [o for o in orders_for(user["username"]) if matches(f'{o["product"]} {o["variant"]} {o["order_id"]} {o["status"]} {o["headline"]}')]
    tickets = my_tickets(user)
    order_ids = {o["order_id"] for o in orders}  # tickets about a matching order count too
    tickets = tickets[tickets.apply(
        lambda r: r["order_id"] in order_ids or matches(f'{r["ticket_id"]} {r["order_id"]} {r["category"]} {r["complaint"]} {r["followup_text"]}'), axis=1
    )] if not tickets.empty else tickets
    articles, _ = search_passages(query)
    st.markdown(
        f'<div class="section-title" style="margin-top:0">Results for “{html.escape(query)}”</div>'
        + chips(*[(f"{n} {word}{'' if n == 1 else 's'}", css) for n, word, css in
                  ((len(orders), "order", ""), (len(tickets), "ticket", ""), (len(articles), "help article", "src"))]),
        unsafe_allow_html=True,
    )
    if not orders and tickets.empty and not articles:
        st.markdown('<div class="empty">Nothing matches that. Try a product name, an order ID such as ORD-4512, or a question like “refund time”.</div>',
                    unsafe_allow_html=True)
        return
    if orders:
        st.markdown('<div class="dash-title">Orders</div>', unsafe_allow_html=True)
        for order in orders:
            with st.container(border=True):
                st.markdown(order_card(order, None), unsafe_allow_html=True)
                _, b = st.columns([5, 1.3])
                if b.button("Need help?", key=f"s_help_{order['order_id']}", width="stretch"):
                    st.session_state["help_order"] = order
                    st.session_state["page"] = "My Orders"
                    st.rerun()
    if not tickets.empty:
        st.markdown('<div class="dash-title">Tickets</div>', unsafe_allow_html=True)
        for _, row in tickets.iterrows():
            label, css, _ = customer_status(row)
            order = f" · {html.escape(row['order_id'])}" if row["order_id"] else ""
            st.markdown(
                f'<div class="card" style="margin-bottom:0.5rem"><div class="review-head"><b>{html.escape(row["ticket_id"])}{order}</b>'
                f'<span class="ticket-status {css}">{label}</span></div>'
                f'<div class="complaint" style="margin-top:0.3rem">{html.escape(row["followup_text"] or row["complaint"])}</div></div>',
                unsafe_allow_html=True,
            )
        if st.button("Open My Tickets", key="s_tickets"):
            go("My Tickets")
    if articles:
        st.markdown('<div class="dash-title">Help articles</div>', unsafe_allow_html=True)
        for hit in articles:
            with st.container(border=True):
                st.markdown(f'<div class="kb-hit" style="margin:0"><b>📄 {html.escape(hit["source"])} › {html.escape(hit["heading"])} · {html.escape(hit["topic"])}</b></div>',
                            unsafe_allow_html=True)
                st.markdown(hit["text"].split("\n", 1)[-1])


def account_header(user: dict, unread: int) -> None:
    """Blue store bar with a working account menu (My Profile, Orders, Wishlist, Notifications, Logout)."""
    with st.container(key="fk_header"):
        logo, search, menu, orders_link, help_link = st.columns([1.25, 3.6, 1.35, 1.05, 1.15], vertical_alignment="center")
        logo.markdown('<div class="fk-logo">ShopNest<small>Support <i>✦</i> AI Desk</small></div>', unsafe_allow_html=True)
        search.text_input(
            "Search", key="hdr_search", placeholder="Search your orders, tickets and help articles",
            label_visibility="collapsed", icon=":material/search:", on_change=_start_search,
        )
        with menu.popover(user["username"], icon=":material/account_circle:", key=f"acct_menu_{st.session_state.get('menu_n', 0)}"):
            st.markdown('<div class="acct-title">Your Account</div>', unsafe_allow_html=True)
            for page, (icon, in_menu) in PAGES.items():
                if not in_menu:
                    continue
                label = "Orders" if page == "My Orders" else page
                if page == "Notifications" and unread:
                    label = f"Notifications ({unread})"
                if st.button(label, key=f"acct_{page}", icon=icon, width="stretch"):
                    go(page)
            if st.button("Logout", key="acct_logout", icon=":material/logout:", width="stretch"):
                for key in list(st.session_state):
                    del st.session_state[key]
                st.rerun()
        if orders_link.button("My Orders", key="hdr_orders", icon=":material/package_2:"):
            go("My Orders")
        if help_link.button("Help Centre", key="hdr_help", icon=":material/help:"):
            go("Help Centre")


def page_nav(current: str) -> None:
    """White menu strip under the header; the current page is underlined in blue."""
    active = NAV.index(current) if current in NAV else -1  # the search page has no menu entry
    st.markdown(
        f"<style>.st-key-nav_{active} button {{border-bottom: 3px solid var(--blue) !important;}}"
        f".st-key-nav_{active} button p {{color: var(--blue) !important;}}</style>",
        unsafe_allow_html=True,
    )
    with st.container(key="fk_nav"):
        cols = st.columns(len(NAV), gap="small")
        for i, page in enumerate(NAV):
            if cols[i].button(page, key=f"nav_{i}", width="stretch") and page != current:
                go(page)


def render_customer(user: dict) -> None:
    with st.sidebar:
        logout_button(user)
        st.markdown(
            '<div class="side-label">How we help</div>'
            '<div class="side-agent"><div class="num">1</div><div class="txt"><b>Pick an order</b><small>Press Need help? on it</small></div></div>'
            '<div class="side-agent"><div class="num">2</div><div class="txt"><b>Tell us the problem</b><small>In your own language</small></div></div>'
            '<div class="side-agent"><div class="num">3</div><div class="txt"><b>Get an answer</b><small>In seconds, or after a specialist checks it</small></div></div>',
            unsafe_allow_html=True,
        )
    page = st.session_state.setdefault("page", "My Orders")
    recent = [n for n in notifications(user) if n["when"] >= f"{date.today() - timedelta(days=7):%Y-%m-%d}"]
    account_header(user, len(recent))
    page_nav(page)
    {
        "My Orders": lambda: render_orders(user),
        "My Tickets": lambda: render_my_tickets(user),
        "Wishlist": lambda: render_wishlist(user),
        "Notifications": lambda: render_notifications(user),
        "Help Centre": render_help_centre,
        "Search": lambda: render_search(user),
        "My Profile": lambda: render_account(user),
    }[page]()
