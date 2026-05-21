"""PDF upload page."""

import pandas as pd
import streamlit as st

from api_client import (
    _api_request,
    _fetch_uploaded_bill_options_api,
    _remember_uploaded_bill_payload,
)


def render() -> None:
    st.markdown(
        '<div class="hero">'
        '<div class="hero-body">'
        '<div class="hero-title">Troy &amp; Banks</div>'
        '<div class="hero-sub">Dominion Energy &nbsp;·&nbsp; Virginia &nbsp;·&nbsp; Enterprise Billing Audit Platform</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload Dominion Energy Billing PDF (select one or more files)",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="usage_bills_pdf_uploader",
    )

    if not uploaded_files:
        st.info(
            "Add one or more Dominion billing PDFs above. When processing finishes you’ll open **Results** to review "
            "**Analysis** or use the sidebar (**Past usage bills**, etc.) without uploading again."
        )

    if not uploaded_files:
        return

    batch_key = "|".join(f"{f.name}_{f.size}" for f in uploaded_files)
    if st.session_state.get("usage_bills_pdf_batch_key") != batch_key:
        st.session_state["usage_bills_pdf_batch_key"] = batch_key
        st.session_state["usage_df"] = None

    if st.session_state.get("usage_df") is not None:
        return

    last_usage = None
    last_profile = None
    last_name = None
    summaries = []
    errors = []
    for uf in uploaded_files:
        try:
            with st.spinner(f"Processing {uf.name} - OCR and database sync"):
                files = {"file": (uf.name, uf.getbuffer(), "application/pdf")}
                r = _api_request("post", "/api/bills/upload", files=files)
                payload = r.json()
            usage_records = payload.get("usage_records") or []
            if not usage_records:
                errors.append("No usage tables extracted from one of the selected files.")
                continue
            from components.tables import standardize_usage_dataframe

            usage_df = standardize_usage_dataframe(pd.DataFrame(usage_records))
            profile = payload.get("profile") or {}
            batch_id = payload.get("batch_id", "")
            summaries.append({"file": uf.name, "batch_id": batch_id, "rows": int(payload.get("rows_uploaded", 0))})
            last_usage, last_profile, last_name = usage_df, profile, uf.name
            _remember_uploaded_bill_payload(payload, usage_df, uf.name)
            _fetch_uploaded_bill_options_api.clear()
            for _key in (
                "pastusage_recalc_account_option",
                "latest_recalc_account_option",
            ):
                st.session_state.pop(_key, None)
        except Exception as e:
            errors.append(str(e))
    for msg in errors:
        st.error(msg)
    if last_usage is None:
        st.stop()
    st.session_state["usage_df"] = last_usage
    st.session_state["profile"] = last_profile or {}
    if len(uploaded_files) == 1:
        st.session_state["pdf_name"] = last_name
    else:
        st.session_state["pdf_name"] = f"{len(uploaded_files)} PDFs (viewing last: {last_name})"
    st.session_state["multi_pdf_summaries"] = summaries

    st.session_state["page"] = "results"
    st.rerun()
