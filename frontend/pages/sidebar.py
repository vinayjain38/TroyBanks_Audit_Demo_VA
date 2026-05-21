"""Sidebar navigation and theme toggle."""

import streamlit as st


def render_sidebar() -> None:
    st.markdown("### Display")
    if "ui_theme_selector" not in st.session_state:
        st.session_state["ui_theme_selector"] = st.session_state.get("ui_theme", "Dark")
    st.radio(
        "Theme",
        options=["Dark", "Light"],
        key="ui_theme_selector",
        horizontal=True,
    )
    st.session_state["ui_theme"] = st.session_state["ui_theme_selector"]
    st.markdown("### Navigate")
    st.markdown(
        '<p class="sidebar-nav-lead">These pages do not share your entries or results.</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload usage bills (PDF)</strong> — <span>Add billing PDFs.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload usage bills", use_container_width=True, key="sidebar_nav_upload_bills"):
        st.session_state["page"] = "upload"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload latest tariff</strong> — <span>Upload the schedules Excel file.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload latest tariff", use_container_width=True, key="sidebar_nav_tariff"):
        st.session_state["page"] = "op_tariff"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload latest riders</strong> — <span>Upload the riders Excel file.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload latest riders", use_container_width=True, key="sidebar_nav_riders"):
        st.session_state["page"] = "op_riders"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Past usage bills (recalculate + export)</strong> — '
        "<span>Run saved usage through selected tariff/rider versions and export.</span></p>",
        unsafe_allow_html=True,
    )
    if st.button("Past usage bills", use_container_width=True, key="sidebar_nav_past"):
        st.session_state["page"] = "op_past"
        st.rerun()
