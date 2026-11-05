"""ShopNest AI Support Desk - Streamlit app with a customer portal and an admin panel.

    streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="ShopNest Support", page_icon="🛍️", layout="wide")

from ui.admin import render_admin  # noqa: E402  (set_page_config must run first)
from ui.customer import render_customer  # noqa: E402
from ui.login import render_login  # noqa: E402
from ui.theme import apply_style  # noqa: E402

apply_style()
user = st.session_state.get("user")
if user is None:
    render_login()
elif user["role"] == "admin":
    render_admin(user)
else:
    render_customer(user)
