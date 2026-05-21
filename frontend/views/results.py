"""Post-upload analysis results page."""

import pandas as pd
import streamlit as st

from components import (
    render_account_usage_charges_section,
    render_anomaly_detection_settings_expander,
    render_rate_compare_tab,
    render_schedule_compare_tab,
    render_usage_results_header,
)
from theme import select_persisted_tab


def render() -> None:
    usage_df: pd.DataFrame = st.session_state.get("usage_df")
    profile: dict = st.session_state.get("profile", {})
    pdf_name: str = st.session_state.get("pdf_name", "Unknown file")

    if usage_df is None:
        st.session_state["page"] = "upload"
        st.rerun()

    from components.tables import standardize_usage_dataframe

    usage_df = standardize_usage_dataframe(usage_df.copy())

    if usage_df.empty:
        st.error("No valid billing records were extracted from the PDF.")
        st.caption("Try another bill file, or use **Back to upload**.")
        if st.button("Back to upload"):
            st.session_state["page"] = "upload"
            st.session_state["usage_df"] = None
            st.session_state["usage_bills_pdf_batch_key"] = None
            st.rerun()
        st.stop()

    contract_id = str(usage_df["contract_account"].iloc[0])
    customer_name = str(usage_df["customer"].iloc[0])

    render_usage_results_header(
        source_label=pdf_name,
        customer_name=customer_name,
        contract_id=contract_id,
        back_button_key="results_nav_back_upload",
    )

    render_anomaly_detection_settings_expander()
    tab_labels = ["Account", "Rate compare", "Schedule compare"]
    selected = select_persisted_tab(tab_labels, "results_analysis_tab")
    if selected == "Account":
        render_account_usage_charges_section(
            usage_df,
            profile=profile,
            widget_key_prefix="",
            show_profile_section=True,
        )
    elif selected == "Rate compare":
        render_rate_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")
    elif selected == "Schedule compare":
        render_schedule_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")
