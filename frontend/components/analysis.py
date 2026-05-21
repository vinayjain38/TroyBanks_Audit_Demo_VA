"""Account, rate compare, and schedule compare tabs."""

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
from .tables import (
    _billing_block,
    _parse_money,
    _st_dataframe,
    account_billing_column_config,
    add_total,
    compute_total_row_from_detail,
    export_excel,
    export_excel_multi_sheet,
    merge_schedule_output,
    merged_comparison_column_config,
    monthly_actual_vs_calculated_gaps,
    monthly_calculated_view_columns,
    monthly_calculated_view_df,
    monthly_view_column_config,
    render_dataframe_with_fixed_total,
    reorder_first,
    schedule_compare_gap_table,
    split_billing_rows_and_total,
)
from .anomalies import (
    build_anomalies_export_table,
    render_anomalies_section,
    render_anomaly_detection_settings_expander,
)


def rider_col_config(df: pd.DataFrame, decimals: int = 6) -> dict:
    return {
        c: st.column_config.NumberColumn(c, format=f"$%.{decimals}f")
        for c in df.columns if re.match(r"^ve\d+_rider_charge$", c)
    }


def kpi_card(label: str, value: str, sub: str = "", cls: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    val_cls = f"kpi-value {cls}".strip()
    return (f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="{val_cls}">{value}</div>'
            f'{sub_html}'
            f'</div>')


def info_item(label: str, value: str) -> str:
    return (f'<div class="info-item">'
            f'<div class="info-item-label">{label}</div>'
            f'<div class="info-item-value">{value or "—"}</div>'
            f'</div>')


def _usage_view_mode_label(label: str, *, active: bool, align: str) -> str:
    state = "usage-mode-active" if active else "usage-mode-inactive"
    return (
        f'<div class="usage-mode-label {state}" '
        f'style="text-align:{align}; padding-top:0.42rem;">{label}</div>'
    )


def render_usage_results_header(
    *,
    source_label: str,
    customer_name: str,
    contract_id: str,
    back_button_key: str,
) -> None:
    """Same top bar as Upload → Results: TROY & BANKS, source · customer · contract, Back to upload."""
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
        if st.button("Back to upload", type="secondary", key=back_button_key):
            st.session_state["page"] = "upload"
            st.session_state["usage_df"] = None
            st.session_state["profile"] = {}
            st.session_state["file_id"] = None
            st.session_state["usage_bills_pdf_batch_key"] = None
            st.rerun()


def render_account_usage_charges_section(
    usage_df: pd.DataFrame,
    *,
    profile: dict | None,
    widget_key_prefix: str = "",
    show_profile_section: bool = True,
) -> None:
    """Profile (optional), Usage & Charges charts/table, anomalies — same as Upload → Results → Account tab."""
    usage_df = usage_df.copy()
    usage_df["bill_period_end"] = pd.to_datetime(usage_df["bill_period_end"], errors="coerce")
    usage_df = usage_df.dropna(subset=["bill_period_end"])
    if usage_df.empty:
        st.warning("No valid billing rows in this view.")
        return

    if show_profile_section:
        if profile:
            st.markdown('<div class="section-title">Profile Details (from PDF)</div>', unsafe_allow_html=True)
            profile_fields = [
                "ACCOUNT NO.", "Account Profile", "Phone Number", "Mailing Address",
                "Service Address", "Customer Class", "Turn On Date",
                "District Office", "Meter Number(s)", "Current Rate",
                "Tax District", "NAICS Code", "Voltage", "Delivery Phase",
                "Minimum Demand", "Facility Charge", "Billing Status", "Key Account Manager",
            ]
            items = [
                info_item(lbl, str(profile[lbl]))
                for lbl in profile_fields
                if lbl in profile and str(profile[lbl]).lower() not in ("nan", "none", "")
            ]
            if items:
                st.markdown('<div class="info-grid">' + "".join(items) + "</div>", unsafe_allow_html=True)
        else:
            st.info("No profile data found in the PDF.")

        st.markdown("<hr>", unsafe_allow_html=True)

    _ktoggle = f"{widget_key_prefix}account_usage_table_toggle"
    _table_only_state = bool(st.session_state.get(_ktoggle, False))

    _utitle, _umode = st.columns([0.62, 0.38])
    with _utitle:
        st.markdown('<div class="section-title">Usage & Charges Over Time</div>', unsafe_allow_html=True)
    with _umode:
        _gcol, _toggle_col, _tcol = st.columns([0.44, 0.12, 0.44], gap="small")
        with _gcol:
            st.markdown(
                _usage_view_mode_label("Graph", active=not _table_only_state, align="right"),
                unsafe_allow_html=True,
            )
        with _toggle_col:
            if hasattr(st, "toggle"):
                _table_only = st.toggle(
                    "Graph or table",
                    value=False,
                    key=_ktoggle,
                    help="Off: monthly charts. On: billing records table.",
                    label_visibility="collapsed",
                )
            else:
                _table_only = st.checkbox(
                    "Graph or table",
                    value=False,
                    key=_ktoggle,
                    help="Off: monthly charts. On: billing records table.",
                    label_visibility="collapsed",
                )
        with _tcol:
            st.markdown(
                _usage_view_mode_label("Table", active=_table_only_state, align="left"),
                unsafe_allow_html=True,
            )
    st.caption(
        "Every calendar month from your first bill through your last bill is shown. "
        "Months with no bill are zero. Multiple bills in one month are summed."
    )
    _raw = usage_df[["bill_period_end", "usage_kwh", "charges"]].copy()
    _raw["bill_period_end"] = pd.to_datetime(_raw["bill_period_end"], errors="coerce")
    _raw = _raw.dropna(subset=["bill_period_end"])
    if _raw.empty:
        chart_df = pd.DataFrame(columns=["bill_period_end", "Usage (kWh)", "Charges ($)"])
    else:
        _raw["_m"] = _raw["bill_period_end"].dt.to_period("M")
        monthly = _raw.groupby("_m", as_index=True)[["usage_kwh", "charges"]].sum()
        _full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
        monthly = monthly.reindex(_full, fill_value=0.0)
        monthly = monthly.copy()
        monthly["bill_period_end"] = monthly.index.to_timestamp()
        monthly = monthly.reset_index(drop=True)
        chart_df = monthly.rename(
            columns={"usage_kwh": "Usage (kWh)", "charges": "Charges ($)"}
        )

    disp_cols = [c for c in ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"] if c in usage_df.columns]
    disp = usage_df[disp_cols].copy()
    disp["bill_period_end"] = disp["bill_period_end"].dt.strftime("%Y-%m-%d")
    disp = disp.rename(columns={
        "bill_period_end": "Bill Period", "current_rate": "Rate",
        "usage_kwh": "Usage (kWh)", "demand_kw": "Demand (kW)", "charges": "Charges ($)",
    })

    _show_chart = not _table_only
    _show_table = _table_only

    if _show_chart:
        if chart_df.empty:
            st.info("No billing dates to chart.")
        else:
            _n_months = len(chart_df)
            c_left, c_right = st.columns(2, gap="medium")
            if alt is not None:
                _axis_x = alt.X(
                    "bill_period_end:T",
                    axis=alt.Axis(
                        format="%b %Y",
                        labelAngle=-45 if _n_months <= 24 else -65,
                        title=None,
                        labelOverlap=False,
                        tickCount=_n_months,
                    ),
                )

                def _usage_charges_theme(chart: alt.Chart) -> alt.Chart:
                    colors = theme_palette()
                    return (
                        chart.properties(
                            height=320 if _n_months > 18 else 280,
                            usermeta={"embedOptions": {"actions": False}},
                        )
                        .configure(background=colors["chart_bg"])
                        .configure_view(stroke=colors["chart_stroke"])
                        .configure_axis(
                            labelColor=colors["axis_label"],
                            titleColor=colors["axis_title"],
                            gridColor=colors["grid"],
                            domainColor=colors["chart_stroke"],
                        )
                    )

                _colors = theme_palette()
                with c_left:
                    st.markdown("**Usage (kWh) by month**")
                    ch_u = _usage_charges_theme(
                        alt.Chart(chart_df)
                        .mark_area(line=True, color=_colors["usage_color"], interpolate="monotone", opacity=0.68)
                        .encode(
                            x=_axis_x,
                            y=alt.Y("Usage (kWh):Q", title="kWh"),
                        )
                    )
                    st.altair_chart(ch_u, use_container_width=True)
                with c_right:
                    st.markdown("**Charges ($) by month**")
                    ch_c = _usage_charges_theme(
                        alt.Chart(chart_df)
                        .mark_area(line=True, color=_colors["charge_color"], interpolate="monotone", opacity=0.68)
                        .encode(
                            x=_axis_x,
                            y=alt.Y("Charges ($):Q", title="$"),
                        )
                    )
                    st.altair_chart(ch_c, use_container_width=True)
            else:
                with c_left:
                    st.markdown("**Usage (kWh) by month**")
                    st.area_chart(chart_df.set_index("bill_period_end")["Usage (kWh)"], color="#c4c4c4")
                with c_right:
                    st.markdown("**Charges ($) by month**")
                    st.area_chart(chart_df.set_index("bill_period_end")["Charges ($)"], color="#9ca3af")
                st.caption("Install **altair** for month names on the horizontal axis (`pip install altair`).")

    if _show_table:
        if chart_df.empty:
            st.info("No monthly billing rows.")
        else:
            c_left, c_right = st.columns(2, gap="medium")
            table_monthly = chart_df.copy()
            table_monthly["bill_period_end"] = pd.to_datetime(
                table_monthly["bill_period_end"], errors="coerce"
            ).dt.strftime("%Y-%m")
            with c_left:
                st.markdown("**Usage (kWh) by month**")
                usage_table = table_monthly[["bill_period_end", "Usage (kWh)"]].rename(
                    columns={"bill_period_end": "Month"}
                )
                _st_dataframe(
                    usage_table,
                    width="stretch",
                    height=420,
                    hide_index=True,
                    column_config={
                        "Month": st.column_config.TextColumn("Month"),
                        "Usage (kWh)": st.column_config.NumberColumn("Usage (kWh)", format="%.0f"),
                    },
                    key=f"{widget_key_prefix}usage_monthly_table",
                )
            with c_right:
                st.markdown("**Charges ($) by month**")
                charges_table = table_monthly[["bill_period_end", "Charges ($)"]].rename(
                    columns={"bill_period_end": "Month"}
                )
                _st_dataframe(
                    charges_table,
                    width="stretch",
                    height=420,
                    hide_index=True,
                    column_config={
                        "Month": st.column_config.TextColumn("Month"),
                        "Charges ($)": st.column_config.NumberColumn("Charges ($)", format="$%.2f"),
                    },
                    key=f"{widget_key_prefix}charges_monthly_table",
                )

        if not disp.empty:
            st.markdown('<div class="section-title">All Billing Records</div>', unsafe_allow_html=True)
            acct_full = pd.concat(
                [disp.reset_index(drop=True), compute_total_row_from_detail(disp, "Bill Period")],
                ignore_index=True,
            )
            acct_cfg = account_billing_column_config(disp)
            render_dataframe_with_fixed_total(
                acct_full,
                period_col="Bill Period",
                column_config=acct_cfg,
                key_prefix=f"{widget_key_prefix}acct_billing",
            )

    render_anomalies_section(
        usage_df,
        view_period_df=usage_df,
        key_suffix=f"{widget_key_prefix}analysis_account",
    )


def render_rate_compare_tab(
    usage_df: pd.DataFrame,
    *,
    contract_id: str,
    widget_key_prefix: str = "",
) -> None:
    """Rate compare tab — same UI as Upload → Results."""
    from .tables import add_total, reorder_first

    kp = widget_key_prefix
    available_years = build_year_options(usage_df)
    rc_y1, rc_y2, _rc_hdr_spacer = st.columns([1, 1, 3])
    with rc_y1:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}rc_year")
    with rc_y2:
        schedule_id = st.selectbox("Schedule", sorted(SCHEDULE_FUNCS.keys()), key=f"{kp}rc_schedule")

    df_year, year_label = filter_by_year_option(usage_df, selected_year)
    df_year_for_anomalies = df_year.copy()
    df_year["bill_period_end"] = df_year["bill_period_end"].dt.strftime("%Y-%m-%d")

    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
    else:
        try:
            schedule_out = SCHEDULE_FUNCS[schedule_id](df_year.copy(), None)
            base_cols = ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"]
            avail = [c for c in base_cols if c in df_year.columns]
            merged = merge_schedule_output(df_year[avail], schedule_out)

            calc_col = f"ve{schedule_id}_calculated_amount"
            actual_total = df_year["charges"].sum()
            calc_total = merged[calc_col].sum() if calc_col in merged.columns else 0
            total_savings = actual_total - calc_total
            savings_cls = "kpi-positive" if total_savings >= 0 else "kpi-negative"
            savings_label = "Total Savings" if total_savings >= 0 else "Total Overpaid"

            rc_kpi_html = (
                kpi_card(f"Actual Charges ({year_label})", f"${actual_total:,.2f}")
                + kpi_card(f"VE-{schedule_id} Calculated", f"${calc_total:,.2f}")
                + kpi_card(savings_label, f"${abs(total_savings):,.2f}", cls=savings_cls)
            )
            st.markdown(
                f'<div class="kpi-row compare-kpi-band">{rc_kpi_html}</div>',
                unsafe_allow_html=True,
            )

            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown('<div class="section-title">Detailed Comparison</div>', unsafe_allow_html=True)
            st.caption("Each billing period with usage, charges, and calculated breakdown; last row is **TOTAL**. Download for full detail.")
            merged_totals = add_total(merged)
            merged_totals = merged_totals.loc[:, ~merged_totals.columns.str.contains("case_type", case=False)]
            merged_totals = reorder_first(merged_totals)

            _rc_key_safe = re.sub(r"[^\w]+", "_", str(year_label))[:32]
            _rc_full_cfg = merged_comparison_column_config(merged_totals)
            render_dataframe_with_fixed_total(
                merged_totals,
                period_col="bill_period_end",
                column_config=_rc_full_cfg,
                key_prefix=f"{kp}rc_full_{schedule_id}_{_rc_key_safe}",
            )
            st.download_button(
                "Download full detail (Excel)",
                data=export_excel(merged_totals),
                file_name=f"{contract_id}_VE{schedule_id}_{year_label}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_full_rc_{schedule_id}_{str(year_label).replace(' ', '_')[:48]}",
            )
            rc_summary = monthly_calculated_view_df(merged_totals)
            st.markdown('<div class="section-title">Monthly summary (period, usage, charges, calculated)</div>', unsafe_allow_html=True)
            st.caption(
                "Shorter table: dates, usage, charges, and key calculated columns. Use **Download full detail** above for everything."
            )
            rc_disp = rc_summary.copy()
            if "bill_period_end" in rc_disp.columns:
                b = rc_disp["bill_period_end"]
                is_tot = b.astype(str).str.upper() == "TOTAL"
                rc_disp = rc_disp.copy()
                rc_disp.loc[~is_tot, "bill_period_end"] = pd.to_datetime(
                    b[~is_tot], errors="coerce"
                ).dt.strftime("%Y-%m-%d")
            render_dataframe_with_fixed_total(
                rc_disp,
                period_col="bill_period_end",
                column_config=monthly_view_column_config(rc_disp),
                key_prefix=f"{kp}rc_sum_{schedule_id}_{_rc_key_safe}",
            )
            st.download_button(
                "Download monthly summary (Excel)",
                data=export_excel(rc_summary),
                file_name=f"{contract_id}_VE{schedule_id}_{year_label}_monthly_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_sum_rc_{schedule_id}_{str(year_label).replace(' ', '_')[:48]}",
            )
            gap_df = monthly_actual_vs_calculated_gaps(merged, calc_col)
            gd_wb = pd.DataFrame()
            if not gap_df.empty:
                st.markdown(
                    '<div class="section-title">Actual vs calculated — monthly gaps</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Per bill: actual minus VE calculated. Positive = billed more than the model; "
                    "**gap %** is vs calculated (not actual)."
                )
                gd = gap_df.copy()
                gd["bill_period_end"] = pd.to_datetime(
                    gd["bill_period_end"], errors="coerce"
                ).dt.strftime("%Y-%m-%d")
                gd_wb = gd.copy()
                _st_dataframe(
                    gd,
                    width="stretch",
                    height=460,
                    hide_index=True,
                    column_config={
                        "bill_period_end": st.column_config.TextColumn("bill_period_end"),
                        "actual_charges": st.column_config.NumberColumn(format="$%.2f"),
                        "calculated": st.column_config.NumberColumn(format="$%.2f"),
                        "gap_actual_minus_calculated": st.column_config.NumberColumn(
                            format="$%.2f",
                        ),
                        "gap_pct_of_calculated": st.column_config.NumberColumn(format="%.1f"),
                    },
                )
                _yl = re.sub(r"[^\w]+", "_", str(year_label))[:32]
                st.download_button(
                    "Download monthly gaps (Excel)",
                    data=export_excel(gd),
                    file_name=f"{contract_id}_VE{schedule_id}_{_yl}_gaps.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{kp}dl_gap_rc_{schedule_id}_{_yl}",
                )
            _yl_wb = re.sub(r"[^\w]+", "_", str(year_label))[:28]
            _wb_rc = {"Full_detail": merged_totals, "Monthly_summary": rc_summary}
            if not gd_wb.empty:
                _wb_rc["Gaps"] = gd_wb
            st.download_button(
                "Download one workbook (all tables on this tab)",
                data=export_excel_multi_sheet(_wb_rc),
                file_name=f"{contract_id}_VE{schedule_id}_{_yl_wb}_workbook.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_wb_rc_{schedule_id}_{_yl_wb}",
            )
            render_anomalies_section(
                usage_df,
                view_period_df=df_year_for_anomalies,
                title=f"Anomalies — {year_label}",
                key_suffix=f"{kp}rc_{schedule_id}_{str(year_label).replace(' ', '_')[:24]}",
            )
        except Exception as e:
            st.error(f"Schedule VE-{schedule_id} error: {e}")


def render_schedule_compare_tab(
    usage_df: pd.DataFrame,
    *,
    contract_id: str,
    widget_key_prefix: str = "",
) -> None:
    """Schedule compare tab — same UI as Upload → Results."""
    from .tables import add_total, reorder_first

    kp = widget_key_prefix
    available_years3 = build_year_options(usage_df)
    ctrl3a, ctrl3b = st.columns([1, 2])
    with ctrl3a:
        selected_year3 = st.selectbox("Year", available_years3, key=f"{kp}sc_year")
    with ctrl3b:
        selected_schedules = st.multiselect(
            "Schedules to Compare",
            options=sorted(SCHEDULE_FUNCS.keys()),
            default=sorted(SCHEDULE_FUNCS.keys()),
            key=f"{kp}sc_schedules",
        )

    df_year3, year_label3 = filter_by_year_option(usage_df, selected_year3)
    df_year3_for_anomalies = df_year3.copy()
    df_year3["bill_period_end"] = df_year3["bill_period_end"].dt.strftime("%Y-%m-%d")

    if not selected_schedules:
        st.warning("Select at least one schedule to compare.")
    elif df_year3.empty:
        st.warning(f"No billing data found for {year_label3}.")
    else:
        actual_total3 = df_year3["charges"].sum()
        base_cols = ["bill_period_end", "usage_kwh", "charges"]
        comp = df_year3[[c for c in base_cols if c in df_year3.columns]].reset_index(drop=True).copy()

        schedule_totals = {}
        for sid in selected_schedules:
            try:
                out = SCHEDULE_FUNCS[sid](df_year3.copy(), None)
                calc_col = f"ve{sid}_calculated_amount"
                label = f"VE-{sid} Calculated ($)"
                if calc_col in out.columns:
                    comp = merge_schedule_output(
                        comp,
                        out[["bill_period_end", calc_col]].rename(columns={calc_col: label}),
                    )
                    schedule_totals[f"VE-{sid}"] = pd.to_numeric(comp[label], errors="coerce").sum()
                else:
                    st.warning(f"Schedule VE-{sid}: calculated_amount column not found.")
            except Exception as e:
                st.warning(f"Schedule VE-{sid} skipped: {e}")

        if schedule_totals:
            sc_kpi_html = kpi_card("Actual Charges", f"${actual_total3:,.2f}", year_label3)
            for sched_name, calc_val in schedule_totals.items():
                diff = actual_total3 - calc_val
                cls = "kpi-positive" if diff >= 0 else "kpi-negative"
                sc_kpi_html += kpi_card(
                    sched_name,
                    f"${calc_val:,.2f}",
                    f"Save ${diff:,.2f}" if diff >= 0 else f"Over ${abs(diff):,.2f}",
                    cls,
                )
            st.markdown(
                f'<div class="kpi-row compare-kpi-band">{sc_kpi_html}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("<hr>", unsafe_allow_html=True)

        st.markdown('<div class="section-title">Monthly calculated amounts</div>', unsafe_allow_html=True)
        st.caption(
            "One calculated column per schedule. **Monthly summary** is the essentials; **full comparison** includes all columns and a **TOTAL** row."
        )
        comp = comp.loc[:, ~comp.columns.str.contains("case_type", case=False)]
        result = reorder_first(add_total(comp))
        summary_sc = monthly_calculated_view_df(result)

        display = summary_sc.copy()
        num_cols = display.select_dtypes(include=["float", "int"]).columns
        display[num_cols] = display[num_cols].round(2)
        if "bill_period_end" in display.columns:
            b = display["bill_period_end"]
            is_tot = b.astype(str).str.upper() == "TOTAL"
            display = display.copy()
            display.loc[~is_tot, "bill_period_end"] = pd.to_datetime(
                b[~is_tot], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
        _sc_key_safe = re.sub(r"[^\w]+", "_", str(year_label3))[:40]
        render_dataframe_with_fixed_total(
            display,
            period_col="bill_period_end",
            column_config=monthly_view_column_config(display),
            key_prefix=f"{kp}sc_monthly_{_sc_key_safe}",
        )
        st.download_button(
            "Download monthly summary (Excel)",
            data=export_excel(summary_sc),
            file_name=f"{contract_id}_schedule_comparison_{year_label3}_monthly_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_sum_sc_{str(year_label3).replace(' ', '_')[:48]}",
        )
        st.download_button(
            "Download full comparison (Excel)",
            data=export_excel(result),
            file_name=f"{contract_id}_schedule_comparison_{year_label3}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_full_sc_{str(year_label3).replace(' ', '_')[:48]}",
        )
        gap_sc = schedule_compare_gap_table(comp, selected_schedules)
        gsd_wb = pd.DataFrame()
        if not gap_sc.empty:
            st.markdown(
                '<div class="section-title">Gaps vs each schedule (actual minus calculated)</div>',
                unsafe_allow_html=True,
            )
            st.caption("Same periods as the table above; one gap column per VE schedule.")
            gsd = gap_sc.copy()
            gsd["bill_period_end"] = pd.to_datetime(
                gsd["bill_period_end"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            gsd_wb = gsd.copy()
            gap_cfg = {}
            for c in gsd.columns:
                if c == "bill_period_end":
                    gap_cfg[c] = st.column_config.TextColumn(c)
                elif "gap_vs" in c:
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
                elif "charges" in c.lower():
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
                elif "usage" in c.lower() or "kwh" in c.lower():
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="%.0f")
                else:
                    gap_cfg[c] = st.column_config.TextColumn(c)
            _st_dataframe(gsd, width="stretch", height=460, hide_index=True, column_config=gap_cfg)
            _y3 = re.sub(r"[^\w]+", "_", str(year_label3))[:32]
            st.download_button(
                "Download schedule gap table (Excel)",
                data=export_excel(gsd),
                file_name=f"{contract_id}_schedule_gaps_{_y3}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_gap_sc_{_y3}",
            )
        _y3_wb = re.sub(r"[^\w]+", "_", str(year_label3))[:28]
        _wb_sc = {"Full_comparison": result, "Monthly_summary": summary_sc}
        if not gsd_wb.empty:
            _wb_sc["Gaps"] = gsd_wb
        st.download_button(
            "Download one workbook (all tables on this tab)",
            data=export_excel_multi_sheet(_wb_sc),
            file_name=f"{contract_id}_schedule_compare_{_y3_wb}_workbook.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_wb_sc_{_y3_wb}",
        )
        render_anomalies_section(
            usage_df,
            view_period_df=df_year3_for_anomalies,
            title=f"Anomalies — {year_label3}",
            key_suffix=f"{kp}sc_{str(year_label3).replace(' ', '_')[:28]}",
        )


def build_year_options(df: pd.DataFrame) -> list:
    years = sorted(df["bill_period_end"].dt.year.dropna().unique().astype(int), reverse=True)
    return ["All Years", "Last 12 Months", *years]


def filter_by_year_option(df: pd.DataFrame, selected_option):
    if selected_option == "All Years":
        return df.copy(), "All Years"

    if selected_option == "Last 12 Months":
        month_periods = df["bill_period_end"].dt.to_period("M")
        latest_month = month_periods.max()
        if pd.isna(latest_month):
            return df.iloc[0:0].copy(), "Last 12 Months"

        start_month = latest_month - 11
        mask = (month_periods >= start_month) & (month_periods <= latest_month)
        label = (
            f"Last 12 Months "
            f"({start_month.to_timestamp().strftime('%b %Y')} – {latest_month.to_timestamp().strftime('%b %Y')})"
        )
        return df[mask].copy(), label

    return df[df["bill_period_end"].dt.year == selected_option].copy(), str(selected_option)





