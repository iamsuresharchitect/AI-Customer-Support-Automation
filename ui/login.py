"""Login page shared by customers and the admin."""

import streamlit as st

import auth
from ui.theme import top_bar


def render_login() -> None:
    top_bar(None, "Search for products, brands and more", "<span>Help Centre</span>")
    _, left, right, _ = st.columns([0.6, 1.6, 2.2, 0.6], gap="small")
    with left:
        st.markdown(
            '<div class="login-side"><div><h2>Login</h2>'
            "<p>Track your orders, raise a complaint and get an answer in seconds, in your own language.</p></div>"
            '<div class="art">🛍️🎧📦</div></div>',
            unsafe_allow_html=True,
        )
    with right, st.form("login"):
        username = st.text_input("Username", placeholder="e.g. priya")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login", width="stretch"):
            user = auth.authenticate(username, password)
            if user:
                st.session_state["user"] = user
                st.rerun()
            st.error("That username and password don't match.")
        st.markdown(
            '<div class="login-hint">Customers sign in with their username; new accounts start with the password '
            f"<b>{auth.DEFAULT_PASSWORD}</b>. The support team signs in as <b>{auth.ADMIN_USERNAME}</b>.</div>",
            unsafe_allow_html=True,
        )
    with right.expander("Demo accounts"):
        st.markdown(
            f"- Admin: **{auth.ADMIN_USERNAME}** / **Admin@123**\n"
            f"- Customers: **priya**, **arjun**, **karthik**, **rahul**, **deepa**, **anu** ... / **{auth.DEFAULT_PASSWORD}**"
        )
