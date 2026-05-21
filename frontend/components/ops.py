"""Tariff/riders upload and past-usage recalculation panels."""

import inspect
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import altair as alt
except ImportError:
    alt = None

from api_client import (
    BACKEND_URL,
    SCHEDULE_FUNCS,
    _api_request,
    _calc_sources,
    _export_bytes_via_api,
    _fetch_uploaded_bill_options_api,
    _pastusage_batches_api_payload,
    _records_clean,
    _remember_uploaded_bill_payload,
    _schedule_options,
    _session_uploaded_bill_options,
    _session_usage_records_for_batches,
    _usage_records_for_api,
    add_recalc_history,
    fetch_saved_bill_profile,
    fetch_uploaded_bill_options,
    fetch_version_options,
)
from theme import select_persisted_tab, theme_palette

from .anomalies import (
    build_anomalies_export_table,
    render_anomaly_detection_settings_expander,
    render_anomalies_section,
)
from .analysis import (
    build_year_options,
    filter_by_year_option,
    kpi_card,
    render_account_usage_charges_section,
)
from .tables import (
    _st_dataframe,
    add_total,
    export_excel,
    export_excel_multi_sheet,
    merged_comparison_column_config,
    monthly_calculated_view_df,
    monthly_view_column_config,
    render_dataframe_with_fixed_total,
    reorder_first,
)


def render_ops_tariff_panel(*, key_prefix: str = "ltariff_") -> None:
    st.markdown('<div class="section-title">TARIFFS VERSION UPLOAD</div>', unsafe_allow_html=True)
    st.markdown('<div class="form-panel"><strong>Required</strong>: Tariff workbook and effective date.</div>', unsafe_allow_html=True)

    tariffs_file = st.file_uploader(
        "Select tariffs Excel file",
        type=["xlsx", "xls"],
        key=f"{key_prefix}tariffs_uploader",
    )
    tariffs_effective_date = st.date_input(
        "Tariff effective date",
        key=f"{key_prefix}tariffs_effective_date",
    )
    if st.button("Upload Tariffs Version", type="primary", key=f"{key_prefix}upload_tariffs_btn"):
        if tariffs_file is None:
            st.warning("Upload a tariffs Excel file first.")
        elif tariffs_effective_date > pd.Timestamp.today().date():
            st.warning("Effective date cannot be in the future.")
        else:
            try:
                safe_name = Path(tariffs_file.name).name
                if not safe_name.lower().endswith((".xlsx", ".xls")):
                    st.warning("Only Excel files are supported.")
                else:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    files = {"file": (safe_name, tariffs_file.getbuffer(), mime)}
                    params = {"effective_date": tariffs_effective_date.isoformat()}
                    _api_request("post", "/api/tariffs/upload", files=files, params=params)
                    try:
                        _schedule_options.clear()
                        _calc_sources.clear()
                    except (AttributeError, TypeError):
                        pass
                    st.success(f"Tariffs uploaded successfully: {safe_name}")
                    st.caption("Tariff workbook is saved and versioned. Use **Upload latest riders** when you are ready.")
            except Exception as exc:
                st.error(f"Tariff upload failed: {exc}")


def render_ops_riders_panel(*, key_prefix: str = "lriders_") -> None:
    st.markdown('<div class="section-title">RIDERS VERSION UPLOAD</div>', unsafe_allow_html=True)
    st.markdown('<div class="form-panel"><strong>Required</strong>: Riders workbook and effective date.</div>', unsafe_allow_html=True)

    riders_file = st.file_uploader(
        "Select riders Excel file",
        type=["xlsx", "xls"],
        key=f"{key_prefix}riders_uploader",
    )
    riders_effective_date = st.date_input(
        "Rider effective date",
        key=f"{key_prefix}riders_effective_date",
    )
    if st.button("Upload Riders Version", type="primary", key=f"{key_prefix}upload_riders_btn"):
        if riders_file is None:
            st.warning("Upload a riders Excel file first.")
        elif riders_effective_date > pd.Timestamp.today().date():
            st.warning("Effective date cannot be in the future.")
        else:
            try:
                safe_name = Path(riders_file.name).name
                if not safe_name.lower().endswith((".xlsx", ".xls")):
                    st.warning("Only Excel files are supported.")
                else:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    files = {"file": (safe_name, riders_file.getbuffer(), mime)}
                    params = {"effective_date": riders_effective_date.isoformat()}
                    _api_request("post", "/api/riders/upload", files=files, params=params)
                    try:
                        _calc_sources.clear()
                    except (AttributeError, TypeError):
                        pass
                    st.success(f"Riders uploaded successfully: {safe_name}")
                    st.caption("Riders workbook is saved and versioned. Open **Past usage bills** to recalculate when you are ready.")
            except Exception as exc:
                st.error(f"Rider upload failed: {exc}")


def render_ops_recalc_panel(
    *,
    key_prefix: str = "pastusage_",
    result_df_key: str = "pastusage_recalc_result_df",
    result_name_key: str = "pastusage_recalc_result_name",
    schedule_ids_key: str = "pastusage_recalc_schedule_ids",
    history_session_key: str = "pastusage_recalc_history",
) -> None:
    st.markdown('<div class="section-title">RUN RECALCULATION</div>', unsafe_allow_html=True)
    st.caption(
        "Pick an account and **billing period** (a single year, last 12 months, or all years). "
        "Then choose rate sources and schedules before you run."
    )

    try:
        bill_options = fetch_uploaded_bill_options()
    except Exception as exc:
        st.error(f"Failed to load uploaded bill options: {exc}")
        bill_options = pd.DataFrame()

    if bill_options.empty:
        st.info(
            "**No saved bills yet.** Add bills from **Upload usage bills**, or continue when your data is available. "
            "Then pick an account and billing period here."
        )
    else:
        display_all = bill_options.copy()
        display_all["bill_year"] = display_all["bill_year"].astype(str)

        acct_choices = (
            display_all.assign(
                _uploaded_sort=pd.to_datetime(display_all["uploaded_at"], errors="coerce"),
                _account_sort=display_all["account_number"].astype(str).str.strip(),
                _customer_sort=display_all["customer_name"].astype(str).str.strip(),
            )
            .groupby(["account_number", "customer_name"], as_index=False, dropna=False)
            .agg(
                uploaded_at=("_uploaded_sort", "max"),
                _account_sort=("_account_sort", "first"),
                _customer_sort=("_customer_sort", "first"),
            )
            .sort_values(["uploaded_at", "_account_sort", "_customer_sort"], ascending=[False, True, True], na_position="last")
            .reset_index(drop=True)
        )
        acct_choices["acct_label"] = (
            acct_choices["account_number"].astype(str).str.strip()
            + " — "
            + acct_choices["customer_name"].astype(str).str.strip()
        )
        acct_labels = acct_choices["acct_label"].tolist()
        _acct_sb_key = f"{key_prefix}recalc_account_option"
        if _acct_sb_key in st.session_state and st.session_state[_acct_sb_key] not in acct_labels:
            del st.session_state[_acct_sb_key]
        selected_label = st.selectbox(
            "Account",
            options=acct_labels,
            key=_acct_sb_key,
        )
        st.caption(
            f"Loaded {len(acct_labels)} saved account(s). Open the dropdown to search by number or name."
        )

        acct_row = acct_choices.loc[acct_choices["acct_label"] == selected_label].iloc[0]

        for_account = display_all[
            (display_all["account_number"].astype(str).str.strip() == str(acct_row["account_number"]).strip())
            & (display_all["customer_name"].astype(str).str.strip() == str(acct_row["customer_name"]).strip())
        ]
        selected_period = "All Years"

        batches_to_load: pd.DataFrame | None = None
        selected_row: pd.Series | None = None

        if selected_period in ("All Years", "Last 12 Months"):
            batches_to_load = for_account.sort_values("uploaded_at", ascending=True, na_position="first")
            if batches_to_load.empty:
                st.warning("No batches found for this account.")
            else:
                selected_row = batches_to_load.iloc[-1]
        else:
            batches = for_account[for_account["bill_year"].astype(str) == str(selected_period)].copy()
            batches["uploaded_at_label"] = batches["uploaded_at"].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else "N/A"
            )

            if batches.empty:
                st.warning("No batch found for this account and calendar year.")
            elif len(batches) == 1:
                selected_row = batches.iloc[0]
                batches_to_load = batches
            else:
                batches["session_label"] = (
                    "Uploaded "
                    + batches["uploaded_at_label"]
                    + " · "
                    + batches["row_count"].astype(str)
                    + " row(s)"
                )
                session_label = st.selectbox(
                    "Upload session (same account and year)",
                    options=batches["session_label"].tolist(),
                    key=f"{key_prefix}recalc_session_option",
                )
                selected_row = batches.loc[batches["session_label"] == session_label].iloc[0]
                batches_to_load = batches.loc[batches["session_label"] == session_label]

        if selected_row is not None and batches_to_load is not None:
            try:
                selected_schedule_ids = sorted(_schedule_options(BACKEND_URL))
            except Exception:
                selected_schedule_ids = ["100", "102", "110", "120", "154"]
            tariff_kind, tariff_payload = "file", None
            rider_kind, rider_payload = "file", None

            if st.button("Run recalculation", type="primary", key=f"{key_prefix}recalc_all_btn"):
                if not selected_schedule_ids:
                    st.warning("Select at least one schedule.")
                else:
                    try:
                        with st.spinner("Running recalculation..."):
                            bid_val = selected_row.get("batch_id")
                            bid_use = (
                                str(bid_val).strip()
                                if bid_val is not None and pd.notna(bid_val)
                                else ""
                            )
                            if tariff_kind == "file":
                                tariff_api_source = "file"
                                tariff_api_version = None
                            else:
                                tariff_api_source = "db"
                                tariff_api_version = int(tariff_payload)

                            if rider_kind == "file":
                                rider_api_source = "file"
                                rider_api_version = None
                            else:
                                rider_api_source = "db"
                                rider_api_version = int(rider_payload)

                            batches_pl = _pastusage_batches_api_payload(batches_to_load)
                            session_usage_records = _session_usage_records_for_batches(batches_to_load)
                            if selected_period == "All Years":
                                period_kw: dict = {"period": "All Years"}
                                period_slug = "all_years"
                                period_hist = "All Years"
                            elif selected_period == "Last 12 Months":
                                period_kw = {"period": "Last 12 Months"}
                                period_slug = "last_12_months"
                                period_hist = "Last 12 Months"
                            else:
                                period_kw = {"calendar_year": int(selected_period)}
                                period_slug = str(int(selected_period))
                                period_hist = str(int(selected_period))

                            body = {
                                "schedule_ids": list(selected_schedule_ids),
                                "tariff_source": tariff_api_source,
                                "tariff_version": tariff_api_version,
                                "rider_source": rider_api_source,
                                "rider_version": rider_api_version,
                                **period_kw,
                            }
                            if session_usage_records is not None:
                                body["usage_records"] = session_usage_records
                            else:
                                body["account_number"] = str(selected_row["account_number"]).strip()
                                body["batches"] = batches_pl
                            r = _api_request("post", "/api/calculate", json=body)
                            recalc_result = pd.DataFrame(r.json()["records"])

                            st.session_state[result_df_key] = recalc_result
                            st.session_state[schedule_ids_key] = list(selected_schedule_ids)
                            batch_ids_for_profile = [
                                str(x.get("batch_id", "")).strip()
                                for _, x in batches_to_load.iterrows()
                                if str(x.get("batch_id", "")).strip()
                            ]
                            st.session_state[f"{key_prefix}recalc_profile"] = fetch_saved_bill_profile(
                                str(selected_row["account_number"]).strip(),
                                batch_ids_for_profile,
                            )
                            st.session_state[f"{key_prefix}recalc_source_label"] = (
                                f"Past usage · {period_hist} · "
                                f"{int(len(batches_to_load))} saved row group(s)"
                            )
                            sched_slug = "_".join(str(s) for s in sorted(selected_schedule_ids))
                            tariff_tag = "disk" if tariff_kind == "file" else f"v{int(tariff_payload)}"
                            rider_tag = "disk" if rider_kind == "file" else f"v{int(rider_payload)}"
                            safe_period = re.sub(r"[^\w\-]+", "_", str(period_slug))[:48]
                            st.session_state[result_name_key] = (
                                f"{selected_row['account_number']}_"
                                f"{safe_period}_"
                                f"tariff_{tariff_tag}_"
                                f"rider_{rider_tag}_"
                                f"ve{sched_slug}.xlsx"
                            )
                            add_recalc_history(
                                {
                                    "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "batch_id": bid_use[:16] if bid_use else "",
                                    "account": str(selected_row["account_number"]),
                                    "year": period_hist[:120],
                                    "tariff": tariff_tag,
                                    "rider": rider_tag,
                                    "schedules": ",".join(str(s) for s in sorted(selected_schedule_ids)),
                                    "rows": int(len(recalc_result)),
                                },
                                session_key=history_session_key,
                            )
                            st.session_state["page"] = "op_past_results"
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Recalculation failed: {exc}")


def _recalc_available_schedules(result_df: pd.DataFrame, schedule_ids: list | None = None) -> list[str]:
    found = []
    for col in result_df.columns:
        m = re.match(r"^ve(\d+)_calculated_amount$", str(col))
        if m:
            found.append(m.group(1))
    if schedule_ids:
        wanted = [str(s) for s in schedule_ids]
        found = [s for s in wanted if s in found]
    return sorted(set(found), key=lambda x: int(x) if str(x).isdigit() else str(x))


def _recalc_filter_by_year(result_df: pd.DataFrame, selected_year) -> tuple[pd.DataFrame, str]:
    df = result_df.copy()
    df["bill_period_end"] = pd.to_datetime(df["bill_period_end"], errors="coerce")
    df = df.dropna(subset=["bill_period_end"])
    return filter_by_year_option(df, selected_year)


def render_recalc_rate_compare_tab(
    result_df: pd.DataFrame,
    *,
    contract_id: str,
    schedule_ids: list | None = None,
    widget_key_prefix: str = "pastusage_recalc_like_",
) -> None:
    from .tables import add_total, reorder_first

    schedules = _recalc_available_schedules(result_df, schedule_ids)
    if not schedules:
        st.info("No calculated schedule columns are available in this recalculation result.")
        return
    kp = widget_key_prefix
    available_years = build_year_options(result_df)
    c_year, c_sched, _sp = st.columns([1, 1, 3])
    with c_year:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}rc_year")
    with c_sched:
        schedule_id = st.selectbox("Schedule", schedules, key=f"{kp}rc_schedule")

    df_year, year_label = _recalc_filter_by_year(result_df, selected_year)
    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
        return

    calc_col = f"ve{schedule_id}_calculated_amount"
    actual_total = pd.to_numeric(df_year.get("charges", 0), errors="coerce").fillna(0).sum()
    calc_total = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce").fillna(0).sum()
    total_savings = actual_total - calc_total
    savings_cls = "kpi-positive" if total_savings >= 0 else "kpi-negative"
    savings_label = "Total Savings" if total_savings >= 0 else "Total Overpaid"
    st.markdown(
        '<div class="kpi-row compare-kpi-band">'
        + kpi_card(f"Actual Charges ({year_label})", f"${actual_total:,.2f}")
        + kpi_card(f"VE-{schedule_id} Calculated", f"${calc_total:,.2f}")
        + kpi_card(savings_label, f"${abs(total_savings):,.2f}", cls=savings_cls)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Detailed Comparison</div>', unsafe_allow_html=True)
    sched_cols = [
        c for c in df_year.columns
        if str(c).startswith(f"ve{schedule_id}_") and "case_type" not in str(c).lower()
    ]
    base_cols = [
        c for c in ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"]
        if c in df_year.columns
    ]
    detailed = df_year[base_cols + sched_cols].copy()
    detailed = reorder_first(add_total(detailed))
    safe_year = re.sub(r"[^\w]+", "_", str(year_label))[:32]
    render_dataframe_with_fixed_total(
        detailed,
        period_col="bill_period_end",
        column_config=merged_comparison_column_config(detailed),
        key_prefix=f"{kp}rc_full_{schedule_id}_{safe_year}",
    )
    st.download_button(
        "Download full detail (Excel)",
        data=export_excel(detailed),
        file_name=f"{contract_id}_VE{schedule_id}_{year_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{kp}dl_full_rc_{schedule_id}_{safe_year}",
    )
    monthly = monthly_calculated_view_df(detailed)
    st.markdown('<div class="section-title">Monthly summary</div>', unsafe_allow_html=True)
    render_dataframe_with_fixed_total(
        monthly,
        period_col="bill_period_end",
        column_config=monthly_view_column_config(monthly),
        key_prefix=f"{kp}rc_sum_{schedule_id}_{safe_year}",
    )
    render_anomalies_section(
        result_df,
        view_period_df=df_year,
        title=f"Anomalies — {year_label}",
        key_suffix=f"{kp}rc_{schedule_id}_{safe_year}",
    )


def render_recalc_schedule_compare_tab(
    result_df: pd.DataFrame,
    *,
    contract_id: str,
    schedule_ids: list | None = None,
    widget_key_prefix: str = "pastusage_recalc_like_",
) -> None:
    from .tables import add_total, reorder_first

    schedules = _recalc_available_schedules(result_df, schedule_ids)
    if not schedules:
        st.info("No calculated schedule columns are available in this recalculation result.")
        return
    kp = widget_key_prefix
    available_years = build_year_options(result_df)
    c_year, c_sched = st.columns([1, 2])
    with c_year:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}sc_year")
    with c_sched:
        selected_schedules = st.multiselect(
            "Schedules to Compare",
            options=schedules,
            default=schedules,
            key=f"{kp}sc_schedules",
        )
    if not selected_schedules:
        st.warning("Select at least one schedule to compare.")
        return

    df_year, year_label = _recalc_filter_by_year(result_df, selected_year)
    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
        return

    actual_total = pd.to_numeric(df_year.get("charges", 0), errors="coerce").fillna(0).sum()
    comp_cols = [c for c in ["bill_period_end", "usage_kwh", "charges"] if c in df_year.columns]
    comp = df_year[comp_cols].copy()
    kpis = kpi_card("Actual Charges", f"${actual_total:,.2f}", year_label)
    for sid in selected_schedules:
        calc_col = f"ve{sid}_calculated_amount"
        calc_val = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce").fillna(0).sum()
        comp[f"VE-{sid} Calculated ($)"] = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce")
        diff = actual_total - calc_val
        cls = "kpi-positive" if diff >= 0 else "kpi-negative"
        kpis += kpi_card(
            f"VE-{sid}",
            f"${calc_val:,.2f}",
            f"Save ${diff:,.2f}" if diff >= 0 else f"Over ${abs(diff):,.2f}",
            cls=cls,
        )
    st.markdown(f'<div class="kpi-row compare-kpi-band">{kpis}</div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Monthly calculated amounts</div>', unsafe_allow_html=True)
    result = reorder_first(add_total(comp))
    safe_year = re.sub(r"[^\w]+", "_", str(year_label))[:32]
    render_dataframe_with_fixed_total(
        result,
        period_col="bill_period_end",
        column_config=monthly_view_column_config(result),
        key_prefix=f"{kp}sc_monthly_{safe_year}",
    )
    base_name = f"{contract_id}_schedule_comparison_{safe_year}"
    st.download_button(
        "Download monthly summary (Excel)",
        data=export_excel(result),
        file_name=f"{base_name}_monthly_summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{kp}dl_sum_sc_{safe_year}",
    )
    render_anomalies_section(
        result_df,
        view_period_df=df_year,
        title=f"Anomalies — {year_label}",
        key_suffix=f"{kp}sc_{safe_year}",
    )


def render_recalc_results_like_upload(
    result_df: pd.DataFrame,
    *,
    result_name: str,
    profile: dict | None,
    source_label: str,
    schedule_ids: list | None,
    key_prefix: str,
) -> None:
    from .tables import standardize_usage_dataframe

    result_df = standardize_usage_dataframe(result_df.copy())
    if result_df.empty:
        st.info("No results yet. Run **Run recalculation** first (pick account, period, sources, then run).")
        return
    contract_id = (
        str(result_df["contract_account"].dropna().iloc[0]).strip()
        if "contract_account" in result_df.columns and not result_df["contract_account"].dropna().empty
        else "Unknown account"
    )
    customer_name = (
        str(result_df["customer"].dropna().iloc[0]).strip()
        if "customer" in result_df.columns and not result_df["customer"].dropna().empty
        else "Unknown customer"
    )
    effective_profile = dict(profile or {})
    if not effective_profile:
        rate = (
            str(result_df["current_rate"].dropna().iloc[-1]).strip()
            if "current_rate" in result_df.columns and not result_df["current_rate"].dropna().empty
            else ""
        )
        first_bill = result_df["bill_period_end"].min().strftime("%Y-%m-%d")
        last_bill = result_df["bill_period_end"].max().strftime("%Y-%m-%d")
        effective_profile = {
            "ACCOUNT NO.": contract_id,
            "Account Profile": customer_name,
            "Current Rate": rate,
            "Billing Status": "Saved usage",
            "Turn On Date": f"{first_bill} to {last_bill}",
        }
    st.markdown('<div class="section-title">RECALCULATION RESULTS</div>', unsafe_allow_html=True)
    nav_left, nav_right = st.columns([4, 1])
    with nav_left:
        st.markdown(
            f'<div class="results-nav">'
            f'<div class="results-nav-left">'
            f'<span class="results-nav-mark" aria-hidden="true"></span>'
            f'<div>'
            f'<div class="results-nav-title">TROY &amp; BANKS</div>'
            f'<div class="results-nav-file">{source_label} &nbsp;·&nbsp; {customer_name} &nbsp;·&nbsp; {contract_id}</div>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("Back to recalculation", type="secondary", key=f"{key_prefix}back_to_recalc"):
            st.session_state["page"] = "op_past"
            st.rerun()
    render_anomaly_detection_settings_expander()
    _past_tab_labels = ["Account", "Rate compare", "Schedule compare", "Downloads"]
    _past_tab = select_persisted_tab(_past_tab_labels, f"{key_prefix}past_results_analysis_tab")
    if _past_tab == "Account":
        render_account_usage_charges_section(
            result_df,
            profile=effective_profile,
            widget_key_prefix=f"{key_prefix}acct_",
            show_profile_section=True,
        )
    elif _past_tab == "Rate compare":
        render_recalc_rate_compare_tab(
            result_df,
            contract_id=contract_id,
            schedule_ids=schedule_ids,
            widget_key_prefix=f"{key_prefix}rate_",
        )
    elif _past_tab == "Schedule compare":
        render_recalc_schedule_compare_tab(
            result_df,
            contract_id=contract_id,
            schedule_ids=schedule_ids,
            widget_key_prefix=f"{key_prefix}sched_",
        )
    elif _past_tab == "Downloads":
        summary = monthly_calculated_view_df(result_df)
        base_name = Path(result_name).stem
        try:
            anom = build_anomalies_export_table(result_df, view_period_df=result_df)
        except Exception:
            anom = pd.DataFrame()
        st.download_button(
            "Download monthly summary (Excel)",
            data=export_excel(summary),
            file_name=f"{base_name}_monthly_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_summary",
        )
        st.download_button(
            "Download full recalculation (Excel)",
            data=export_excel(result_df),
            file_name=result_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_full",
        )
        st.download_button(
            "Download one workbook (monthly + full + anomalies)",
            data=export_excel_multi_sheet(
                {
                    "Monthly_summary": summary,
                    "Full_recalculation": result_df,
                    "Anomalies": anom,
                }
            ),
            file_name=f"{base_name}_workbook_monthly_full_anomalies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_workbook",
        )


def render_ops_export_panel(
    *,
    key_prefix: str = "pastusage_",
    result_df_key: str = "pastusage_recalc_result_df",
    result_name_key: str = "pastusage_recalc_result_name",
    schedule_ids_key: str = "pastusage_recalc_schedule_ids",
    history_session_key: str = "pastusage_recalc_history",
    anomalies_key_suffix: str = "pastusage_export",
) -> None:
    result_df = st.session_state.get(result_df_key)
    result_name = st.session_state.get(result_name_key, "recalculation.xlsx")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        render_recalc_results_like_upload(
            result_df,
            result_name=result_name,
            profile=st.session_state.get(f"{key_prefix}recalc_profile", {}),
            source_label=st.session_state.get(f"{key_prefix}recalc_source_label", "Past usage recalculation"),
            schedule_ids=st.session_state.get(schedule_ids_key) or [],
            key_prefix=f"{key_prefix}recalc_results_",
        )
    else:
        st.info(
            "No results yet. Run **Run recalculation** first (pick account, period, sources, then run). "
            "Downloads and anomalies appear here when finished."
        )

    run_history = st.session_state.get(history_session_key, [])
    if run_history:
        st.markdown('<div class="section-title">Recent recalculation runs</div>', unsafe_allow_html=True)
        hist_df = pd.DataFrame(run_history)
        _st_dataframe(hist_df, width="stretch", hide_index=True)
        st.download_button(
            "Download run history (Excel)",
            data=export_excel(hist_df),
            file_name="recalc_run_history.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_history_download",
        )


def render_past_usage_bills_page() -> None:
    """Past usage recalculation form."""
    render_ops_recalc_panel()


def render_past_usage_results_page() -> None:
    """Dedicated results page for past usage recalculation."""
    render_ops_export_panel()

