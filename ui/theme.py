"""Shared look of the app: the store palette, the stylesheet and the blue top bar."""

import html
import re

import streamlit as st

# Store palette: Flipkart-style blue for single-series charts, a one-hue blue ramp for ordered levels,
# orange for escalations, and the fixed status colors (always labelled).
INK = "#212121"
MUTED = "#878787"
GRID = "#EEEEEE"
BLUE = "#2874F0"
ORANGE = "#FB641B"
URGENCY_COLORS = {"Low": "#9CC0F9", "Medium": "#2874F0", "High": "#123F8C"}
SENTIMENT_COLORS = {"Positive": "#cde2fb", "Neutral": "#9ec5f4", "Frustrated": "#5598e7", "Angry": "#256abf", "Very Angry": "#104281"}
STATUS_COLORS = {"Resolved": "#388E3C", "Escalated": "#D32F2F"}


def rate_color(rate: float) -> str:
    """Deeper blue for categories the AI handles well, lighter where humans step in more."""
    return "#123F8C" if rate >= 0.75 else "#2874F0" if rate >= 0.4 else "#9CC0F9"

STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,400;0,500;0,700;1,700;1,900&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #F1F3F6; --panel: #FFFFFF; --line: #E0E0E0; --line-strong: #C2C2C2; --ink: #212121; --muted: #878787;
  --blue: #2874F0; --yellow: #FFE11B; --orange: #FB641B; --amber: #FF9F00;
  --shadow: 0 1px 2px 0 rgba(0,0,0,0.16); --shadow-up: 0 4px 16px 0 rgba(0,0,0,0.12);
  --good: #388E3C; --good-bg: #E7F4E8; --bad: #D32F2F; --bad-bg: #FDECEC;
}
html, body, [class*="css"], .stMarkdown, .stTextInput, .stTextArea, .stSelectbox, button, h1, h2, h3 {font-family: 'Roboto', Arial, sans-serif !important;}
.stApp {background: var(--bg);}
.block-container {padding-top: 1.2rem; max-width: 1280px;}
[data-testid="stHeader"] {background: transparent;}
/* Sidebar */
[data-testid="stSidebar"] {background: #FFFFFF; border-right: none; box-shadow: var(--shadow);}
.side-brand {display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.3rem;}
.side-brand .logo {width: 40px; height: 40px; border-radius: 4px; background: var(--blue); display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; color: var(--yellow);}
.side-brand .name {font-weight: 900; font-style: italic; font-size: 1.2rem; color: var(--blue); line-height: 1.15;}
.side-brand .name small {display: block; font-style: italic; font-weight: 500; font-size: 0.75rem; color: var(--muted);}
.side-status {display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--good); margin: 0.6rem 0 0.4rem; font-weight: 500;}
.side-status:before {content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--good);}
.side-label {font-size: 0.72rem; letter-spacing: 0.6px; text-transform: uppercase; color: var(--muted); font-weight: 500; margin: 1.3rem 0 0.6rem;}
.side-agent {display: flex; gap: 0.7rem; align-items: flex-start; padding: 0.6rem 0.2rem; border-bottom: 1px solid #F0F0F0; margin-bottom: 0.1rem;}
.side-agent .num {flex: 0 0 26px; height: 26px; border-radius: 50%; background: var(--blue); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 500;}
.side-agent .txt b {display: block; color: var(--ink); font-size: 0.86rem; font-weight: 500;}
.side-agent .txt small {color: var(--muted); font-size: 0.75rem; line-height: 1.35;}
[data-testid="stSidebar"] [data-testid="stExpander"] {background: #FFFFFF; border: 1px solid var(--line); border-radius: 2px;}
/* Store header: blue top bar, category strip and promo banner */
.fk-top {background: var(--blue); border-radius: 2px 2px 0 0; padding: 0.7rem 1.4rem; display: flex; align-items: center; gap: 1.6rem; flex-wrap: wrap;}
.fk-logo {color: #fff; font-weight: 900; font-style: italic; font-size: 1.45rem; line-height: 1; text-decoration: none;}
.fk-logo small {display: flex; align-items: center; gap: 0.25rem; font-size: 0.72rem; font-weight: 700; color: #FFFFFF; margin-top: 0.15rem;}
.fk-logo small i {color: var(--yellow);}
.fk-search {flex: 1; min-width: 220px; max-width: 560px; background: #fff; border-radius: 2px; padding: 0.55rem 1rem; color: var(--muted); font-size: 0.88rem;
  box-shadow: 0 2px 4px 0 rgba(0,0,0,0.23);}
.fk-links {display: flex; gap: 1.6rem; color: #fff; font-weight: 500; font-size: 0.95rem; align-items: center;}
.fk-links .pill {background: #fff; color: var(--blue); padding: 0.35rem 1.4rem; border-radius: 2px; font-weight: 500;}
.fk-cats {background: #fff; box-shadow: var(--shadow); display: flex; justify-content: space-around; flex-wrap: wrap; gap: 0.6rem; padding: 0.9rem 1rem 0.7rem; margin-bottom: 0.8rem;}
.fk-cat {text-align: center; min-width: 110px;}
.fk-cat .ic {width: 56px; height: 56px; margin: 0 auto 0.35rem; border-radius: 50%; background: #F0F5FF; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;}
.fk-cat b {display: block; font-size: 0.86rem; font-weight: 500; color: var(--ink);}
.fk-cat small {color: var(--muted); font-size: 0.72rem;}
.fk-arrow {align-self: center; color: var(--line-strong); font-size: 1.3rem; padding-bottom: 1.2rem;}
.fk-banner {position: relative; overflow: hidden; border-radius: 2px; box-shadow: var(--shadow); margin-bottom: 1rem; padding: 1.6rem 2rem; color: #fff;
  background: linear-gradient(100deg, #1F5FD6 0%, #2874F0 45%, #4A90F7 100%); display: flex; justify-content: space-between; align-items: center; gap: 1.5rem; flex-wrap: wrap;}
.fk-banner:after {content: ""; position: absolute; right: -60px; top: -80px; width: 280px; height: 280px; border-radius: 50%; background: rgba(255,225,27,0.18);}
.fk-banner .tag {display: inline-block; background: var(--yellow); color: #212121; font-weight: 700; font-size: 0.72rem; padding: 0.2rem 0.6rem; border-radius: 2px; letter-spacing: 0.4px;}
.fk-banner h1 {color: #fff; font-size: 2rem; font-weight: 700; margin: 0.5rem 0 0.3rem; padding: 0; line-height: 1.15;}
.fk-banner p {color: #E3EDFF; margin: 0; max-width: 640px; font-size: 0.95rem;}
.fk-offers {display: flex; gap: 0.7rem; flex-wrap: wrap; position: relative; z-index: 1;}
.fk-offer {background: #fff; color: var(--ink); border-radius: 2px; padding: 0.7rem 1rem; min-width: 130px; box-shadow: 0 2px 6px rgba(0,0,0,0.18);}
.fk-offer b {display: block; color: var(--good); font-size: 1.15rem;}
.fk-offer small {color: var(--muted); font-size: 0.75rem;}
/* Tabs: white strip with a blue underline, like a store menu */
[role="tablist"] {gap: 0; background: #FFFFFF; padding: 0 0.5rem; border-radius: 2px; box-shadow: var(--shadow); border: none !important;}
[role="tablist"] [role="tab"] {border-radius: 0 !important; padding: 0.8rem 1.4rem !important; border: none !important; border-bottom: 3px solid transparent !important;}
[role="tablist"] [role="tab"] p {font-weight: 500; font-size: 0.95rem; color: var(--ink);}
[role="tablist"] [role="tab"][aria-selected="true"] {border-bottom-color: var(--blue) !important; background: transparent !important;}
[role="tablist"] [role="tab"][aria-selected="true"] p {color: var(--blue) !important;}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {display: none;}
/* Panels and inputs */
[data-testid="stForm"], .card {background: var(--panel); border: none; border-radius: 2px; padding: 1.4rem 1.5rem; box-shadow: var(--shadow);}
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {border-radius: 2px !important; background: #FFFFFF !important; border-color: var(--line) !important;}
.stButton button, .stDownloadButton button {border-radius: 2px; border: 1px solid var(--line); background: #FFFFFF; color: var(--ink); font-weight: 500;
  box-shadow: var(--shadow); text-transform: uppercase; font-size: 0.85rem; padding: 0.5rem 1.2rem;}
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button {border-radius: 2px; padding: 0.7rem 2.2rem; font-weight: 500; border: none; color: #fff;
  background: var(--orange); box-shadow: 0 1px 2px 0 rgba(0,0,0,0.2); text-transform: uppercase; letter-spacing: 0.3px;}
.stButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover {background: #F05A14; color: #fff;}
.st-key-FormSubmitter-complaint-Cancel button, .st-key-FormSubmitter-complaint-Cancel button:hover {background: #fff; color: var(--ink); border: 1px solid var(--line); box-shadow: var(--shadow);}
.stDownloadButton button {background: var(--amber); color: #fff; border: none;}
.stDownloadButton button:hover {background: #F39400; color: #fff;}
.section-title {font-size: 1.15rem; font-weight: 500; color: var(--ink); margin: 1.2rem 0 0.7rem; padding-left: 0.6rem; border-left: 4px solid var(--blue);}
/* Agent pipeline */
.step {display: flex; gap: 1rem; background: var(--panel); border-radius: 2px; padding: 1rem 1.2rem; margin-bottom: 0.7rem; box-shadow: var(--shadow);}
.step .dot {flex: 0 0 40px; height: 40px; border-radius: 50%; background: #F0F5FF; display: flex; align-items: center; justify-content: center; font-size: 1.1rem;}
.step .body {flex: 1; min-width: 0;}
.step .head {display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem;}
.step .name {font-weight: 500; color: var(--ink);}
.step .done {color: #fff; background: var(--good); font-size: 0.72rem; font-weight: 500; white-space: nowrap; padding: 0.1rem 0.5rem; border-radius: 3px;}
.step .role {color: var(--muted); font-size: 0.8rem; margin-bottom: 0.55rem;}
.step .out {font-family: ui-monospace, Menlo, Consolas, monospace; background: #F8F9FB; border: 1px solid #EEEEEE; border-radius: 2px;
  padding: 0.7rem 0.9rem; word-break: break-word; font-size: 0.78rem; color: #3A3A3A; max-height: 260px; overflow: auto;}
/* Result */
.badge {display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.8rem; border-radius: 3px; font-weight: 500; font-size: 0.9rem; color: #fff;}
.badge-resolved {background: var(--good);}
.badge-escalated {background: var(--bad);}
.reason {color: var(--muted); font-size: 0.85rem; margin-top: 0.55rem;}
.meta {display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0;}
.meta span {background: #FFFFFF; border: 1px solid var(--line); border-radius: 2px; padding: 0.25rem 0.7rem; font-size: 0.78rem; color: var(--ink);}
.meta span b {color: var(--muted); font-weight: 400;}
.reply {background: #FFFFFF; border: 1px solid var(--line); border-left: 4px solid var(--blue); border-radius: 2px; padding: 1.1rem 1.3rem;
  line-height: 1.65; color: var(--ink); font-size: 0.95rem;}
.reply p {margin: 0 0 0.7rem;} .reply p:last-child {margin: 0;}
.foot {color: var(--muted); font-size: 0.8rem; margin-top: 0.7rem;}
.handoff {margin-top: 0.9rem; background: #FFF7E6; color: #8A5300; border: 1px solid #FFE0A3; border-radius: 2px; padding: 0.6rem 0.9rem; font-size: 0.85rem;}
.review-head {display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;}
.review-head b {color: var(--ink); font-size: 1.05rem; font-weight: 500;}
.complaint {color: var(--ink); font-size: 0.92rem; margin: 0.6rem 0 0.2rem;}
.pending {background: #FFF7E6; color: #8A5300; border: 1px solid #FFE0A3; border-radius: 3px; padding: 0.2rem 0.7rem; font-size: 0.78rem; font-weight: 500;}
.empty {color: var(--muted); text-align: center; padding: 3rem 1rem; border-radius: 2px; background: var(--panel); box-shadow: var(--shadow);}
/* KPI cards */
.kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.8rem; margin: 0.8rem 0 1rem;}
.kpi {position: relative; background: var(--panel); border-radius: 2px; padding: 1.1rem 1.3rem; overflow: hidden; box-shadow: var(--shadow);}
.kpi .top {display: flex; justify-content: space-between; align-items: center;}
.kpi .icon {width: 36px; height: 36px; border-radius: 50%; background: #F0F5FF; display: flex; align-items: center; justify-content: center; font-size: 1rem;}
.kpi .label {font-size: 0.78rem; color: var(--muted); font-weight: 500;}
.kpi .value {font-size: 2.1rem; font-weight: 500; color: var(--ink); line-height: 1.1; margin-top: 0.35rem;}
.kpi .sub {font-size: 0.8rem; color: var(--muted);}
.kpi .bar {height: 4px; border-radius: 2px; background: #EEEEEE; margin-top: 0.7rem; overflow: hidden;}
.kpi .bar span {display: block; height: 100%; background: var(--blue);}
@media (max-width: 900px) {.kpis {grid-template-columns: repeat(2, minmax(0, 1fr));} .fk-banner h1 {font-size: 1.5rem;} .fk-arrow {display: none;}}
[data-testid="stPlotlyChart"] {background: var(--panel); border-radius: 2px; padding: 0.6rem 0.4rem; box-shadow: var(--shadow);}
[data-testid="stDataFrame"] {border-radius: 2px; overflow: hidden; box-shadow: var(--shadow);}
/* Bordered Streamlit containers become white store cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {background: #fff; border: none !important; border-radius: 2px; box-shadow: var(--shadow);}
/* Login */
.login-side {background: var(--blue); color: #fff; border-radius: 2px 0 0 2px; padding: 2.2rem 2rem; min-height: 470px; display: flex; flex-direction: column; justify-content: space-between;}
.login-side h2 {color: #fff; font-size: 1.8rem; font-weight: 500; margin: 0 0 0.8rem;}
.login-side p {color: #DBE7FF; font-size: 1.05rem; line-height: 1.5; margin: 0;}
.login-side .art {font-size: 3.4rem; text-align: center; letter-spacing: 0.6rem;}
.login-hint {color: var(--muted); font-size: 0.8rem; margin-top: 0.6rem;}
/* Customer orders page */
.crumb {color: var(--muted); font-size: 0.78rem; margin: 0.2rem 0 0.6rem;}
.filter-title {font-size: 1.15rem; font-weight: 500; color: var(--ink); padding-bottom: 0.6rem; border-bottom: 1px solid #F0F0F0; margin-bottom: 0.4rem;}
.filter-label {font-size: 0.8rem; font-weight: 500; color: var(--ink); text-transform: uppercase; margin: 0.8rem 0 0.2rem;}
.order {display: grid; grid-template-columns: 72px minmax(0, 3fr) minmax(70px, 1fr) minmax(0, 3fr); gap: 1rem; align-items: start;}
.order .pic {width: 72px; height: 72px; display: flex; align-items: center; justify-content: center; font-size: 2.6rem; background: #F8F9FB; border-radius: 2px;}
.order .prod b {display: block; font-weight: 400; color: var(--ink); font-size: 0.95rem;}
.order .prod small {color: var(--muted); font-size: 0.8rem;}
.order .price {color: var(--ink); font-size: 0.95rem;}
.order .stat b {font-weight: 500; font-size: 0.92rem; color: var(--ink); display: flex; align-items: center; gap: 0.45rem;}
.order .stat small {display: block; color: var(--muted); font-size: 0.8rem; margin: 0.25rem 0 0 1.1rem;}
.tone {width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: 0 0 9px;}
.tone-good {background: #26A541;} .tone-warn {background: #FF9F00;} .tone-bad {background: #FF6161;} .tone-neutral {background: #878787;}
.tchip {display: inline-block; margin-top: 0.5rem; background: #F0F5FF; color: var(--blue); border: 1px solid #C9DCFD; border-radius: 2px; font-size: 0.75rem; padding: 0.15rem 0.5rem;}
.tchip.wait {background: #FFF7E6; color: #8A5300; border-color: #FFE0A3;}
.tchip.done {background: var(--good-bg); color: var(--good); border-color: #BFE3C4;}
.ticket-status {display: inline-block; border-radius: 3px; padding: 0.15rem 0.6rem; font-size: 0.78rem; font-weight: 500; color: #fff;}
.ts-answered {background: var(--good);} .ts-review {background: var(--amber);} .ts-closed {background: #878787;}
/* Admin ticket status cards */
.tk-grid {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.9rem; margin: 0.4rem 0 1rem;}
.tk-card {background: var(--panel); border-radius: 4px; box-shadow: var(--shadow); padding: 1rem 1.1rem 0.9rem; border-top: 4px solid var(--c);
  display: flex; flex-direction: column; gap: 0.5rem; transition: box-shadow 0.15s, transform 0.15s; --c: var(--blue); --cbg: #F0F5FF;}
.tk-card:hover {box-shadow: var(--shadow-up); transform: translateY(-2px);}
.tk-answered {--c: var(--good); --cbg: var(--good-bg);}
.tk-waiting {--c: var(--amber); --cbg: #FFF7E6;}
.tk-approved {--c: var(--blue); --cbg: #F0F5FF;}
.tk-closed {--c: #878787; --cbg: #F2F2F2;}
.tk-head {display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;}
.tk-id {font-weight: 700; color: var(--ink); font-size: 0.98rem; margin-right: 0.5rem;}
.tk-cat {font-size: 0.78rem; color: var(--muted); white-space: nowrap;}
.tk-status {background: var(--cbg); color: var(--c); font-size: 0.74rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 12px; white-space: nowrap;
  border: 1px solid color-mix(in srgb, var(--c) 30%, transparent);}
.tk-waiting .tk-status {color: #8A5300;}
.tk-when {font-size: 0.76rem; color: var(--muted); margin-top: -0.25rem;}
.tk-text {color: var(--ink); font-size: 0.9rem; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  background: #FAFBFC; border-left: 3px solid var(--line); padding: 0.45rem 0.65rem; border-radius: 2px;}
.tk-who {display: flex; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; font-size: 0.84rem; color: var(--ink);}
.tk-who b {font-weight: 500;} .tk-who small {color: var(--muted);}
.tk-chips {display: flex; flex-wrap: wrap; gap: 0.35rem;}
.tk-chip {font-size: 0.72rem; padding: 0.12rem 0.55rem; border-radius: 12px; background: #F3F4F6; color: var(--ink); border: 1px solid #E5E7EB;}
.tk-chip.urg-high {background: var(--bad-bg); color: var(--bad); border-color: #F7C9C9; font-weight: 600;}
.tk-chip.urg-medium {background: #FFF7E6; color: #8A5300; border-color: #FFE0A3;}
.tk-chip.urg-low {background: var(--good-bg); color: var(--good); border-color: #C5E5C7;}
.tk-reason {font-size: 0.8rem; color: #8A5300; background: #FFF7E6; border-radius: 2px; padding: 0.35rem 0.6rem;}
.tk-closed .tk-reason {color: var(--muted); background: #F5F5F5;}
.tk-card details {border-top: 1px dashed var(--line); padding-top: 0.45rem; margin-top: auto;}
.tk-card summary {cursor: pointer; color: var(--blue); font-size: 0.82rem; font-weight: 500;}
.tk-reply {font-size: 0.85rem; line-height: 1.5; color: var(--ink); margin-top: 0.45rem; max-height: 220px; overflow-y: auto;}
.tk-by {font-size: 0.74rem; color: var(--muted); margin-top: 0.35rem;}
@media (max-width: 1200px) {.tk-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}}
@media (max-width: 700px) {.tk-grid {grid-template-columns: 1fr;}}
.help-box {background: #F0F5FF; border: 1px solid #C9DCFD; border-radius: 2px; padding: 0.7rem 1rem; color: var(--ink); font-size: 0.88rem; margin-bottom: 0.6rem;}
.hello {font-size: 0.85rem; color: var(--muted);} .hello b {display: block; color: var(--ink); font-size: 1rem; font-weight: 500;}
.stat-row {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.8rem; margin: 0.6rem 0 1rem;}
@media (max-width: 900px) {.order {grid-template-columns: 56px 1fr;} .order .price, .order .stat {grid-column: 2;} .stat-row {grid-template-columns: repeat(2, minmax(0, 1fr));}}
/* Customer timeline, badges and help centre */
.tl-wait {background: #fff; border: 1px dashed var(--line-strong); border-radius: 4px; padding: 0.65rem 1rem; color: var(--muted); font-size: 0.9rem; margin-bottom: 0.5rem;}
.chips {display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0;}
.chip {display: inline-block; border-radius: 12px; padding: 0.15rem 0.65rem; font-size: 0.78rem; font-weight: 500; background: #EEF3FD; color: var(--blue); border: 1px solid #D5E2FB;}
.chip.src {background: #FFF8E1; color: #8A6100; border-color: #FFE7A3;}
.chip.high {background: var(--bad-bg); color: var(--bad); border-color: #F7C9C9;}
.chip.ok {background: var(--good-bg); color: var(--good); border-color: #C5E5C7;}
.kb-hit {border-left: 3px solid var(--amber); background: #FFFDF5; padding: 0.5rem 0.8rem; margin: 0.4rem 0; font-size: 0.86rem; color: var(--ink);}
.kb-hit b {display: block; font-size: 0.8rem; color: #8A6100; margin-bottom: 0.2rem;}
.kb-doc {font-size: 0.8rem; color: var(--muted); margin: -0.2rem 0 0.4rem;}
/* Customer header with account menu, page menu, profile, notifications */
.st-key-fk_header {background: var(--blue); border-radius: 2px; padding: 0.55rem 1.2rem; margin-bottom: 0.2rem;}
.st-key-fk_header .fk-search {max-width: none;}
.st-key-fk_header [data-testid="stPopover"] button {background: #fff !important; color: var(--blue) !important; border: none !important; border-radius: 2px !important; font-weight: 500;}
.st-key-fk_header [data-testid="stPopover"] button p {color: var(--blue) !important; font-weight: 500;}
.st-key-hdr_orders button, .st-key-hdr_help button {background: transparent !important; border: none !important; box-shadow: none !important; color: #fff !important; padding: 0.3rem 0.2rem !important; white-space: nowrap;}
.st-key-hdr_orders button p, .st-key-hdr_help button p {color: #fff !important; font-weight: 500; font-size: 0.95rem; text-transform: none;}
[data-testid="stPopoverBody"] {min-width: 260px; padding: 0.6rem 0.4rem !important;}
[data-testid="stPopoverBody"] .acct-title {font-weight: 700; color: var(--ink); padding: 0.2rem 0.8rem 0.4rem; font-size: 0.95rem;}
[data-testid="stPopoverBody"] button {justify-content: flex-start !important; border: none !important; background: transparent !important; box-shadow: none !important; padding: 0.45rem 0.8rem !important; min-height: 0 !important;}
[data-testid="stPopoverBody"] button > div {justify-content: flex-start !important; width: 100%;}
[data-testid="stPopoverBody"] button:hover {background: #EEF3FD !important;}
[data-testid="stPopoverBody"] button p {color: var(--ink) !important; font-size: 0.92rem; text-transform: none; letter-spacing: 0;}
[data-testid="stPopoverBody"] [data-testid="stElementContainer"] {margin-bottom: -0.6rem;}
.st-key-fk_nav {background: #fff; box-shadow: var(--shadow); border-radius: 2px; padding: 0 0.5rem; margin-bottom: 0.6rem;}
.st-key-fk_nav button {background: transparent !important; border: none !important; border-bottom: 3px solid transparent !important; border-radius: 0 !important; box-shadow: none !important; padding: 0.7rem 0.3rem !important;}
.st-key-fk_nav button p {color: var(--ink) !important; font-weight: 500; font-size: 0.93rem; text-transform: none; letter-spacing: 0;}
.profile-head {display: flex; align-items: center; gap: 0.9rem;}
.profile-head .avatar {width: 52px; height: 52px; border-radius: 50%; background: var(--blue); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; font-weight: 700;}
.profile-head small {display: block; color: var(--muted); font-size: 0.8rem;}
.profile-head b {font-size: 1.1rem; color: var(--ink);}
.act-row {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem;}
.act-row div {background: #F5F8FF; border-radius: 4px; padding: 0.6rem; text-align: center;}
.act-row b {display: block; font-size: 1.3rem; color: var(--blue);}
.act-row small {color: var(--muted); font-size: 0.78rem;}
.notif {display: flex; gap: 0.9rem; align-items: center;}
.notif .ic {font-size: 1.5rem; width: 40px; text-align: center;}
.notif b {display: block; font-weight: 500; color: var(--ink); font-size: 0.93rem;}
.notif small {color: var(--muted); font-size: 0.78rem;}
.agent-raw-label {font-size: 0.72rem; letter-spacing: 0.5px; text-transform: uppercase; color: var(--muted); font-weight: 500; margin: 0.7rem 0 0.2rem;}
.done-box {display: flex; gap: 0.8rem; align-items: center; background: var(--good-bg); border: 1px solid #C5E5C7; border-radius: 4px; padding: 0.8rem 1rem;}
.done-box .ic {width: 34px; height: 34px; border-radius: 50%; background: var(--good); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700;}
.done-box b {display: block; color: var(--good); font-size: 1rem;}
.done-box small {color: var(--ink); font-size: 0.85rem;}
/* Animated agent pipeline (motion infographic) */
.pl-box {position: relative; overflow: hidden; border-radius: 12px; padding: 1rem 1.4rem 1.2rem; margin: 0.3rem 0 0.9rem; color: #fff;
  background: linear-gradient(120deg, #0B2A6B, #1F5FD6 55%, #2874F0); box-shadow: 0 6px 20px rgba(17,63,140,0.25);}
.pl-box:before {content: ""; position: absolute; width: 340px; height: 340px; border-radius: 50%; top: -170px; left: -120px;
  background: radial-gradient(circle, rgba(255,225,27,0.22), transparent 70%); animation: plDrift 9s ease-in-out infinite alternate;}
.pl-box.finished {background: linear-gradient(120deg, #0B4A2E, #1E8E4E 55%, #2EB85C);}
.pl-head {position: relative; font-size: 0.82rem; font-weight: 500; letter-spacing: 0.3px; opacity: 0.95; margin-bottom: 0.9rem; display: flex; align-items: center; gap: 0.5rem;}
.pl-head .dot {width: 8px; height: 8px; border-radius: 50%; background: #FFE11B; animation: plBlink 1s ease-in-out infinite;}
.pl-box.finished .pl-head .dot {background: #B9F6CA; animation: none;}
.pl-row {position: relative; display: flex; align-items: flex-start;}
.pl-node {flex: 0 0 116px; text-align: center; animation: plIn 0.5s ease both;}
.pl-node .orb {position: relative; width: 62px; height: 62px; margin: 0 auto; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 1.65rem; background: rgba(255,255,255,0.12); border: 2px solid rgba(255,255,255,0.35); transition: all 0.4s;}
.pl-node.wait .orb {filter: grayscale(0.6); opacity: 0.75;}
.pl-node.active .orb {background: #fff; border-color: #FFE11B; animation: plPulse 1.3s ease-in-out infinite;}
.pl-node.active .orb:after {content: ""; position: absolute; inset: -9px; border-radius: 50%; border: 3px solid transparent; border-top-color: #FFE11B; border-right-color: #FFE11B; animation: plSpin 0.9s linear infinite;}
.pl-node.done .orb {background: #fff; border-color: #B9F6CA; animation: plPop 0.45s ease;}
.pl-node.done .orb:before {content: "✓"; position: absolute; right: -5px; top: -5px; width: 22px; height: 22px; border-radius: 50%; background: #2EB85C; color: #fff;
  font-size: 0.75rem; font-weight: 700; display: flex; align-items: center; justify-content: center; border: 2px solid #fff;}
.pl-node .name {font-weight: 600; font-size: 0.86rem; margin-top: 0.6rem;}
.pl-node .state {font-size: 0.72rem; opacity: 0.8;}
.pl-node.active .state {color: #FFE11B; opacity: 1;}
.pl-linkwrap {flex: 1; margin-top: 29px; min-width: 40px;}
.pl-link {position: relative; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.2); overflow: hidden;}
.pl-link.done {background: rgba(185,246,202,0.9);}
.pl-link.flowing:after {content: ""; position: absolute; top: 0; left: -30%; width: 30%; height: 100%; border-radius: 2px;
  background: linear-gradient(90deg, transparent, #FFE11B, #fff); animation: plPacket 1.1s linear infinite; animation-delay: var(--d, 0s);}
.pl-box.finished .pl-link.flowing:after {background: linear-gradient(90deg, transparent, #fff); animation-duration: 2.2s;}
.pl-tag {text-align: center; font-size: 0.68rem; opacity: 0.75; margin-top: 0.45rem; white-space: nowrap;}
@keyframes plPacket {from {left: -30%;} to {left: 100%;}}
@keyframes plSpin {to {transform: rotate(360deg);}}
@keyframes plPulse {0%, 100% {box-shadow: 0 0 0 0 rgba(255,225,27,0.55);} 50% {box-shadow: 0 0 0 14px rgba(255,225,27,0);}}
@keyframes plPop {0% {transform: scale(0.8);} 70% {transform: scale(1.08);} 100% {transform: scale(1);}}
@keyframes plBlink {50% {opacity: 0.3;}}
@keyframes plIn {from {opacity: 0; transform: translateY(8px);} to {opacity: 1; transform: none;}}
@keyframes plDrift {to {transform: translate(520px, 120px);}}
@media (max-width: 760px) {.pl-node {flex-basis: 70px;} .pl-node .orb {width: 46px; height: 46px; font-size: 1.2rem;} .pl-linkwrap {margin-top: 21px;} .pl-tag {display: none;} .pl-node .name {font-size: 0.72rem;}}
/* Infographic dashboard */
.dash-hero {position: relative; overflow: hidden; display: flex; justify-content: space-between; align-items: center; gap: 1.5rem; flex-wrap: wrap;
  border-radius: 14px; padding: 1.6rem 2rem; margin: 0.6rem 0 1.1rem; color: #fff; background: linear-gradient(120deg, #0B2A6B, #1F5FD6 55%, #3B86F7);
  box-shadow: 0 8px 24px rgba(17,63,140,0.25); animation: plIn 0.5s ease both;}
.dash-hero:before {content: ""; position: absolute; width: 380px; height: 380px; right: -120px; top: -190px; border-radius: 50%; background: radial-gradient(circle, rgba(255,225,27,0.25), transparent 70%);}
.hero-main {position: relative;}
.hero-kicker {font-size: 0.75rem; letter-spacing: 1.2px; text-transform: uppercase; opacity: 0.8; font-weight: 500;}
.hero-num {font-size: 3.6rem; font-weight: 700; line-height: 1; margin: 0.3rem 0 0.2rem;}
.hero-sub {opacity: 0.85; font-size: 0.92rem;}
.hero-chips {display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.9rem;}
.hero-chips span {background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.25); border-radius: 14px; padding: 0.2rem 0.75rem; font-size: 0.8rem;}
.hero-rings {position: relative; display: flex; gap: 1.6rem; flex-wrap: wrap;}
.ring {position: relative; width: 132px; text-align: center;}
.ring svg {width: 104px; height: 104px; transform: rotate(-90deg); display: block; margin: 0 auto;}
.ring .track {fill: none; stroke: rgba(255,255,255,0.18); stroke-width: 9;}
.ring .arc {fill: none; stroke-width: 9; stroke-linecap: round; animation: ringDraw 1.4s cubic-bezier(.2,.8,.2,1) both;}
.ring-val {position: absolute; top: 34px; left: 0; right: 0; font-size: 1.45rem; font-weight: 700;}
.ring-label {font-weight: 600; font-size: 0.85rem; margin-top: 0.45rem;}
.ring-cap {font-size: 0.7rem; opacity: 0.75; line-height: 1.3;}
@keyframes ringDraw {from {stroke-dashoffset: var(--c);}}
.dash-title {font-weight: 600; font-size: 1rem; color: var(--ink); margin: 1.1rem 0 0.6rem;}
.journey {display: flex; align-items: stretch; gap: 0.3rem;}
.jr-step {flex: 1; background: #fff; border-radius: 12px; padding: 0.9rem 1rem; box-shadow: var(--shadow); animation: plIn 0.5s ease both; transition: transform .2s;}
.jr-step:hover, .cat-tile:hover {transform: translateY(-3px); box-shadow: var(--shadow-up);}
.jr-ic {width: 38px; height: 38px; border-radius: 10px; background: #EEF3FD; display: flex; align-items: center; justify-content: center; font-size: 1.15rem;}
.jr-val {font-size: 1.8rem; font-weight: 700; color: var(--ink); margin-top: 0.4rem; line-height: 1.1;}
.jr-label {font-weight: 600; font-size: 0.86rem; color: var(--ink);}
.jr-cap {font-size: 0.74rem; color: var(--muted); min-height: 2.1em;}
.jr-bar {height: 5px; border-radius: 3px; background: #EEF1F6; margin-top: 0.5rem; overflow: hidden;}
.jr-bar span, .ib-track span {display: block; height: 100%; border-radius: 3px; background: var(--blue); animation: barGrow 1.1s cubic-bezier(.2,.8,.2,1) both;}
.jr-arrow {align-self: center; color: var(--blue); font-size: 1.6rem; font-weight: 700; opacity: 0.5; animation: plBlink 1.6s ease-in-out infinite;}
@keyframes barGrow {from {width: 0;}}
.cat-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.8rem;}
.cat-tile {background: #fff; border-radius: 12px; padding: 1rem 1.1rem; box-shadow: var(--shadow); animation: plIn 0.5s ease both; transition: transform .2s;}
.cat-top {display: flex; justify-content: space-between; align-items: center;}
.cat-ic {width: 42px; height: 42px; border-radius: 12px; background: linear-gradient(135deg, #EEF3FD, #DCE8FD); display: flex; align-items: center; justify-content: center; font-size: 1.3rem;}
.cat-share {font-size: 0.78rem; font-weight: 600; color: var(--blue); background: #EEF3FD; border-radius: 10px; padding: 0.1rem 0.55rem;}
.cat-num {font-size: 2rem; font-weight: 700; color: var(--ink); margin-top: 0.5rem; line-height: 1;}
.cat-name {font-size: 0.88rem; color: var(--ink); font-weight: 500; margin-bottom: 0.6rem;}
.cat-rate small {font-size: 0.72rem; color: var(--muted);}
.ib-track {flex: 1; height: 8px; border-radius: 4px; background: #EEF1F6; overflow: hidden;}
.cat-rate .ib-track {height: 6px; margin-bottom: 0.3rem;}
.info-card {background: #fff; border-radius: 12px; padding: 1.1rem 1.3rem; box-shadow: var(--shadow); height: 100%; animation: plIn 0.5s ease both;}
.st-key-dash_volume {background: #fff; border-radius: 12px !important; box-shadow: var(--shadow); border: none !important;}
.seg-bar {display: flex; gap: 2px; height: 22px; border-radius: 6px; overflow: hidden; animation: barGrow 1.1s ease both;}
.seg-bar span {display: block; min-width: 6px;}
.legend {display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.6rem;}
.legend .lg {display: flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; color: var(--ink);}
.legend .lg i {width: 10px; height: 10px; border-radius: 3px; display: inline-block;}
.legend .lg b {color: var(--muted); font-weight: 500; margin-left: 0.15rem;}
.langs {display: flex; flex-wrap: wrap; gap: 0.5rem;}
.lang {display: flex; align-items: center; gap: 0.45rem; border: 1px solid var(--line); border-radius: 18px; padding: 0.2rem 0.75rem 0.2rem 0.25rem; font-size: 0.84rem; color: var(--ink);}
.lang span {width: 26px; height: 26px; border-radius: 50%; background: var(--blue); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 700;}
.lang b {color: var(--muted); font-weight: 500;}
.ib-row {display: grid; grid-template-columns: minmax(120px, 1.3fr) 2fr 82px; gap: 0.8rem; align-items: center; padding: 0.45rem 0;}
.ib-label {font-size: 0.86rem; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.ib-val {font-size: 0.8rem; color: var(--muted); text-align: right;}
.ib-val b {color: var(--ink);}
@media (max-width: 900px) {.journey {flex-direction: column;} .jr-arrow {transform: rotate(90deg);} .hero-rings {gap: 0.6rem;} .ring {width: 110px;}}
.st-key-hdr_search [data-baseweb="input"], .st-key-adm_search [data-baseweb="input"] {background: #fff; border: none; border-radius: 2px; box-shadow: 0 2px 4px rgba(0,0,0,0.23);}
.st-key-hdr_search input, .st-key-adm_search input {font-size: 0.9rem; color: var(--ink);}
/* Rich agent output cards */
.ao-card {background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(16,24,40,0.08), 0 1px 2px rgba(16,24,40,0.04); border: 1px solid #EEF1F6;
  margin-bottom: 0.7rem; overflow: hidden; animation: plIn 0.45s ease both; border-left: 4px solid var(--blue);}
.ao-card.query_agent {border-left-color: #7C4DFF;} .ao-card.knowledge_agent {border-left-color: #F59E0B;}
.ao-card.resolution_agent {border-left-color: #2874F0;} .ao-card.log_agent {border-left-color: #10B981;}
.ao-card.wait {border-left-color: #D0D5DD; opacity: 0.7; box-shadow: none; border-style: dashed;}
.ao-head {display: flex; align-items: center; gap: 0.8rem; padding: 0.8rem 1.1rem;}
.ao-icon {width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.25rem; background: #F2F4F7;}
.query_agent .ao-icon {background: #F1EBFF;} .knowledge_agent .ao-icon {background: #FFF4DE;} .resolution_agent .ao-icon {background: #E8F0FE;} .log_agent .ao-icon {background: #E3F8EF;}
.ao-title {flex: 1;}
.ao-title small {display: block; font-size: 0.72rem; color: var(--muted); letter-spacing: 0.2px;}
.ao-title b {font-size: 0.98rem; font-weight: 600; color: var(--ink);}
.ao-done {font-size: 0.74rem; font-weight: 600; color: #067647; background: #ECFDF3; border-radius: 12px; padding: 0.18rem 0.65rem;}
.ao-wait {font-size: 0.74rem; color: var(--muted); background: #F2F4F7; border-radius: 12px; padding: 0.18rem 0.65rem;}
.ao-body {padding: 0 1.1rem 0.7rem 1.1rem;}
.ao-tiles {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.55rem;}
.ao-tile {display: flex; align-items: center; gap: 0.55rem; background: #F8F9FC; border-radius: 10px; padding: 0.55rem 0.7rem;}
.ao-tile .ao-ic {font-size: 1.15rem;}
.ao-tile small {display: block; font-size: 0.68rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;}
.ao-tile b {font-size: 0.9rem; font-weight: 600; color: var(--ink);}
.ao-tile.bad {background: #FEF3F2;} .ao-tile.bad b {color: #B42318;}
.ao-tile.warn {background: #FFFAEB;} .ao-tile.warn b {color: #B54708;}
.ao-tile.ok {background: #ECFDF3;} .ao-tile.ok b {color: #067647;}
.ao-quote {margin-top: 0.6rem; font-size: 0.86rem; color: #475467; font-style: italic;}
.ao-sub {font-size: 0.76rem; color: var(--muted); margin-bottom: 0.4rem;}
.ao-hit {display: flex; align-items: flex-start; gap: 0.7rem; padding: 0.55rem 0; border-top: 1px solid #F2F4F7;}
.ao-rank {flex: 0 0 24px; height: 24px; border-radius: 50%; background: #FFF4DE; color: #B54708; font-weight: 700; font-size: 0.75rem; display: flex; align-items: center; justify-content: center;}
.ao-hit-body {flex: 1; min-width: 0;}
.ao-hit-title {font-weight: 600; font-size: 0.88rem; color: var(--ink);}
.ao-doc {font-weight: 400; color: var(--muted); font-size: 0.78rem;}
.ao-hit-text {font-size: 0.82rem; color: #475467; margin-top: 0.1rem;}
.ao-hit-meta {display: flex; gap: 0.3rem; flex-wrap: wrap; justify-content: flex-end; max-width: 210px;}
.ao-pill {font-size: 0.68rem; font-weight: 600; border-radius: 10px; padding: 0.12rem 0.5rem; background: #F2F4F7; color: #344054; white-space: nowrap;}
.ao-pill.topic {background: #EEF3FD; color: var(--blue);} .ao-pill.vector {background: #F1EBFF; color: #5925DC;} .ao-pill.keyword {background: #FFF4DE; color: #B54708;}
.ao-pill.bad {background: #FEF3F2; color: #B42318;}
.ao-reply {font-size: 0.88rem; color: var(--ink); background: #F8F9FC; border-radius: 10px; padding: 0.7rem 0.9rem; line-height: 1.5;}
.ao-reply.held {color: #475467; background: #FFFAEB;}
.ao-row {display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-top: 0.55rem;}
.ao-row .chips {margin: 0;}
.ao-meter {display: flex; align-items: center; gap: 0.25rem; font-size: 0.78rem; color: var(--muted);}
.ao-meter span {margin-right: 0.25rem;}
.ao-meter i {width: 16px; height: 6px; border-radius: 3px; background: #EAECF0; display: inline-block;}
.ao-meter i.on {background: #12B76A;}
.ao-meter b {color: var(--ink); margin-left: 0.3rem; font-weight: 600;}
.ao-log {display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;}
.ao-ticket small {display: block; font-size: 0.68rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;}
.ao-ticket b {font-size: 1.25rem; font-weight: 700; color: var(--ink); letter-spacing: 0.3px;}
.ao-status {font-size: 0.82rem; font-weight: 600; border-radius: 8px; padding: 0.35rem 0.75rem;}
.ao-status.ok {background: #ECFDF3; color: #067647;} .ao-status.bad {background: #FEF3F2; color: #B42318;}
.ao-reasons {display: flex; gap: 0.3rem; flex-wrap: wrap;}
.ao-empty {font-size: 0.86rem; color: #475467;}
.ao-raw {border-top: 1px solid #F2F4F7; padding: 0.45rem 1.1rem;}
.ao-raw summary {cursor: pointer; font-size: 0.74rem; color: var(--muted); font-weight: 500; list-style: none;}
.ao-raw summary:before {content: "{ } "; color: var(--blue); font-weight: 700;}
.ao-raw div {margin-top: 0.5rem; font-family: "JetBrains Mono", Consolas, monospace; font-size: 0.74rem; color: #344054; background: #F8F9FC; border-radius: 8px; padding: 0.6rem 0.8rem; max-height: 220px; overflow: auto;}
@media (max-width: 760px) {.ao-tiles {grid-template-columns: repeat(2, minmax(0, 1fr));} .ao-hit-meta {display: none;}}
</style>
"""


def apply_style() -> None:
    # Blank lines would end the HTML block in Markdown and print the CSS as text, so drop them.
    st.markdown(re.sub(r"\n\s*\n", "\n", STYLE), unsafe_allow_html=True)


def top_bar(user: dict | None, search_hint: str, links: str = "") -> None:
    """Blue store bar: logo, a search-style strip (decoration) and links on the right."""
    who = f'<span class="pill">{html.escape(user["name"])}</span>' if user else ""
    st.markdown(
        '<div class="fk-top" style="border-radius:2px;margin-bottom:0.8rem"><div class="fk-logo">ShopNest<small>Support <i>✦</i> AI Desk</small></div>'
        f'<div class="fk-search">🔍 &nbsp;{html.escape(search_hint)}</div>'
        f'<div class="fk-links">{who}{links}</div></div>',
        unsafe_allow_html=True,
    )
