"""Troy & Banks audit UI entry point."""

import streamlit as st

import config  # noqa: F401 — loads .env and BACKEND_URL
from pages import ops, results, upload
from pages.sidebar import render_sidebar
from theme import (
    apply_global_dark_styles,
    apply_light_override_styles,
    finalize_theme,
    init_theme_state,
)

# ---------------------------------------------------
# Page config & theme
# ---------------------------------------------------
init_theme_state()
st.set_page_config(page_title="Troy & Banks", layout="wide")
apply_global_dark_styles()

# ---------------------------------------------------
# Session state defaults
# ---------------------------------------------------
if "page" not in st.session_state:
    st.session_state["page"] = "upload"

for _ak, _av in (
    ("anom_yoy_pct", 0.5),
    ("anom_abs_daily", 5.0),
    ("anom_bill_mult", 2.5),
    ("anom_bill_delta_cpk", 0.05),
    ("anom_bill_min_kwh", 30.0),
    ("anom_charge_mult", 2.5),
    ("anom_charge_min_usd", 100.0),
):
    st.session_state.setdefault(_ak, _av)

if st.session_state.get("page") == "operations_hub":
    st.session_state["page"] = "op_past"

with st.sidebar:
    render_sidebar()

apply_light_override_styles()

# ---------------------------------------------------
# Page routing
# ---------------------------------------------------
page = st.session_state["page"]

if page == "upload":
    upload.render()
elif page == "op_tariff":
    ops.render_tariff()
elif page == "op_riders":
    ops.render_riders()
elif page == "op_past":
    ops.render_past_usage()
elif page == "op_past_results":
    ops.render_past_usage_results()
elif page == "results":
    results.render()
else:
    st.session_state["page"] = "upload"
    st.rerun()

finalize_theme()
