"""Anomaly detection settings and export tables."""

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
from .tables import _st_dataframe, export_excel, export_excel_multi_sheet


def anomaly_params_from_session() -> dict:
    return {
        "pct_spike_limit": float(st.session_state.get("anom_yoy_pct", 0.5)),
        "abs_spike_limit": float(st.session_state.get("anom_abs_daily", 5.0)),
        "billing_median_multiplier": float(st.session_state.get("anom_bill_mult", 2.5)),
        "billing_min_delta_cpk": float(st.session_state.get("anom_bill_delta_cpk", 0.05)),
        "billing_min_kwh": float(st.session_state.get("anom_bill_min_kwh", 30.0)),
        "charge_median_multiplier": float(st.session_state.get("anom_charge_mult", 2.5)),
        "charge_min_usd": float(st.session_state.get("anom_charge_min_usd", 100.0)),
    }


def render_anomaly_detection_settings_expander() -> None:
    with st.expander("Anomaly detection settings", expanded=False):
        st.caption(
            "Applies to every Anomalies table in Analysis and on **Past usage bills**. "
            "Other automated jobs may still use their own defaults."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "YoY usage spike (fraction above same-month median daily kWh)",
                0.1,
                1.0,
                value=float(st.session_state.get("anom_yoy_pct", 0.5)),
                step=0.05,
                key="anom_yoy_pct",
                help="e.g. 0.50 = 50% higher than historical median for that month",
            )
            st.number_input(
                "Min. absolute daily kWh increase (usage spike)",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.get("anom_abs_daily", 5.0)),
                step=0.5,
                key="anom_abs_daily",
            )
            st.number_input(
                "Billing $/kWh: multiplier vs account median",
                min_value=1.0,
                max_value=10.0,
                value=float(st.session_state.get("anom_bill_mult", 2.5)),
                step=0.1,
                key="anom_bill_mult",
            )
            st.number_input(
                "Billing $/kWh: min. $/kWh above median",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("anom_bill_delta_cpk", 0.05)),
                step=0.01,
                format="%.2f",
                key="anom_bill_delta_cpk",
            )
        with c2:
            st.number_input(
                "Billing $/kWh: minimum usage (kWh) to evaluate",
                min_value=0.0,
                max_value=5000.0,
                value=float(st.session_state.get("anom_bill_min_kwh", 30.0)),
                step=10.0,
                key="anom_bill_min_kwh",
            )
            st.number_input(
                "Charge spike: multiplier vs median bill ($)",
                min_value=1.0,
                max_value=10.0,
                value=float(st.session_state.get("anom_charge_mult", 2.5)),
                step=0.1,
                key="anom_charge_mult",
            )
            st.number_input(
                "Charge spike: minimum bill amount ($)",
                min_value=0.0,
                max_value=5000.0,
                value=float(st.session_state.get("anom_charge_min_usd", 100.0)),
                step=25.0,
                key="anom_charge_min_usd",
            )


def _strip_total_and_parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Drop TOTAL rows and coerce bill_period_end for anomaly logic."""
    if df is None or df.empty or "bill_period_end" not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    mask = d["bill_period_end"].astype(str).str.upper() != "TOTAL"
    d = d.loc[mask]
    d["bill_period_end"] = pd.to_datetime(d["bill_period_end"], errors="coerce")
    return d.dropna(subset=["bill_period_end"])


def _billing_days_by_account(s: pd.Series) -> pd.Series:
    d = s.diff().dt.days.astype(float)
    med = d.median()
    if pd.isna(med) or float(med) < 1:
        med = 30.0
    return d.fillna(med).clip(lower=1)


def _local_anomalies_export_table(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Local fallback when the running backend does not yet expose POST /api/anomalies."""
    df = _strip_total_and_parse_dates(usage_full_history)
    if df.empty:
        return pd.DataFrame()

    p = anomaly_params_from_session()
    if "contract_account" in df.columns:
        df["account"] = df["contract_account"].astype(str).str.strip()
    elif "account_number" in df.columns:
        df["account"] = df["account_number"].astype(str).str.strip()
    else:
        df["account"] = "Single_Account"

    for col in ("usage_kwh", "charges"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else np.nan
    df = df.dropna(subset=["usage_kwh"])
    df = df[df["usage_kwh"] >= 0].copy()
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["account", "bill_period_end"]).reset_index(drop=True)
    df["billing_days"] = df.groupby("account", group_keys=False)["bill_period_end"].transform(
        _billing_days_by_account
    )
    df["daily_kwh"] = np.where(df["billing_days"] > 0, df["usage_kwh"] / df["billing_days"], np.nan)
    df["month"] = df["bill_period_end"].dt.month
    df["same_month_median_daily_kwh"] = df.groupby(["account", "month"])["daily_kwh"].transform("median")
    usage_delta = df["daily_kwh"] - df["same_month_median_daily_kwh"]
    usage_ratio = np.where(
        df["same_month_median_daily_kwh"] > 0,
        usage_delta / df["same_month_median_daily_kwh"],
        0.0,
    )
    df["usage_spike"] = (
        (df.groupby(["account", "month"])["daily_kwh"].transform("count") > 1)
        & (usage_ratio >= float(p["pct_spike_limit"]))
        & (usage_delta >= float(p["abs_spike_limit"]))
    )
    first_seen = df.groupby("account")["bill_period_end"].transform("min")
    df["new_activation"] = df["bill_period_end"].eq(first_seen)

    df["$/kWh"] = np.where(df["usage_kwh"] > 0, df["charges"] / df["usage_kwh"], np.nan)
    med_cpk = df.groupby("account")["$/kWh"].transform("median")
    df["billing_outlier"] = (
        (df["usage_kwh"] >= float(p["billing_min_kwh"]))
        & med_cpk.notna()
        & (med_cpk > 0)
        & (df["$/kWh"] > (med_cpk * float(p["billing_median_multiplier"])))
        & (df["$/kWh"] > med_cpk + float(p["billing_min_delta_cpk"]))
    )
    med_charge = df.groupby("account")["charges"].transform("median")
    df["charge_spike"] = (
        (df["charges"] >= float(p["charge_min_usd"]))
        & med_charge.notna()
        & (med_charge > 0)
        & (df["charges"] > float(p["charge_median_multiplier"]) * med_charge)
    )

    mask = df["usage_spike"] | df["new_activation"] | df["billing_outlier"] | df["charge_spike"]
    out = df.loc[mask].copy()
    if out.empty:
        return pd.DataFrame()

    def _notes(row):
        parts = []
        if bool(row.get("usage_spike")):
            normal = row.get("same_month_median_daily_kwh")
            current = row.get("daily_kwh")
            if pd.notna(normal) and normal > 0 and pd.notna(current):
                pct = ((current - normal) / normal) * 100
                parts.append(f"Spike of {pct:.1f}%. Current usage is {current:.1f} kWh/day vs historical normal of {normal:.1f} kWh/day.")
            else:
                parts.append("Usage is unusually high for this account.")
        if bool(row.get("new_activation")):
            parts.append("New activation or first bill in available history.")
        if bool(row.get("billing_outlier")) and pd.notna(row.get("$/kWh")):
            parts.append(f"Billing: ${row['$/kWh']:.4f}/kWh vs typical median ${med_cpk.loc[row.name]:.4f}/kWh for this account.")
        if bool(row.get("charge_spike")) and pd.notna(row.get("charges")):
            parts.append(f"Charge: ${row['charges']:,.2f} vs typical median bill ${med_charge.loc[row.name]:,.2f}.")
        return " ".join(parts).strip()

    out["notes"] = out.apply(_notes, axis=1)
    if view_period_df is not None and not view_period_df.empty:
        vp = _strip_total_and_parse_dates(view_period_df)
        if not vp.empty:
            out = out[(out["bill_period_end"] >= vp["bill_period_end"].min()) & (out["bill_period_end"] <= vp["bill_period_end"].max())]

    if out.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "bill_period_end": out["bill_period_end"].dt.strftime("%Y-%m-%d"),
            "account": out["account"].astype(str),
            "usage_kwh": out["usage_kwh"],
            "charges": out["charges"],
            "$/kWh": pd.to_numeric(out["$/kWh"], errors="coerce").round(4),
            "usage_spike": out["usage_spike"],
            "new_activation": out["new_activation"],
            "billing_outlier": out["billing_outlier"],
            "charge_spike": out["charge_spike"],
            "notes": out["notes"],
        }
    ).reset_index(drop=True)


def build_anomalies_export_table(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Same grid as the Anomalies table / Excel download (for multi-sheet workbooks)."""
    pe = _strip_total_and_parse_dates(usage_full_history)
    if pe.empty:
        return pd.DataFrame()
    p = anomaly_params_from_session()
    payload = {
        "usage_records": _usage_records_for_api(pe),
        "pct_spike_limit": p["pct_spike_limit"],
        "abs_spike_limit": p["abs_spike_limit"],
        "billing_median_multiplier": p["billing_median_multiplier"],
        "billing_min_delta_cpk": p["billing_min_delta_cpk"],
        "billing_min_kwh": p["billing_min_kwh"],
        "charge_median_multiplier": p["charge_median_multiplier"],
        "charge_min_usd": p["charge_min_usd"],
    }
    if view_period_df is not None and not view_period_df.empty:
        vp = _strip_total_and_parse_dates(view_period_df)
        if not vp.empty:
            payload["view_records"] = _usage_records_for_api(vp)
    try:
        r = requests.post(f"{BACKEND_URL}/api/anomalies", json=payload, timeout=600)
        if r.status_code == 404:
            return _local_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        return _local_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
    except requests.exceptions.HTTPError:
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = (getattr(r, "text", None) or "").strip()
        raise RuntimeError(f"{r.status_code} {r.reason}" + (f" — {detail}" if detail else "")) from None
    records = r.json().get("records") or []
    if not records:
        return pd.DataFrame()
    disp = pd.DataFrame(records)
    if "bill_period_end" in disp.columns:
        disp["bill_period_end"] = pd.to_datetime(disp["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    return disp


def render_anomalies_section(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
    title: str = "Anomalies (usage YoY and billing)",
    key_suffix: str = "",
) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    st.caption(
        "Flags unusual year-over-year usage, new usage patterns, atypical $/kWh, or a bill much larger than your norm. "
        "Tune rules in **Anomaly detection settings** above."
    )
    try:
        disp = build_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
    except Exception as exc:
        st.warning(f"Could not compute anomalies: {exc}")
        return

    if disp.empty:
        st.info(
            "No anomalies in this view for the current rules. "
            "Try widening thresholds in **Anomaly detection settings**, or pick a different period."
        )
        return
    cfg = {
        "charges": st.column_config.NumberColumn("charges", format="$%.2f"),
        "usage_kwh": st.column_config.NumberColumn("usage_kwh", format="%.0f"),
        "$/kWh": st.column_config.NumberColumn("$/kWh", format="%.4f"),
        "usage_spike": st.column_config.CheckboxColumn("usage spike"),
        "new_activation": st.column_config.CheckboxColumn("new activation"),
        "billing_outlier": st.column_config.CheckboxColumn("billing $/kWh"),
        "charge_spike": st.column_config.CheckboxColumn("charge vs median"),
        "notes": st.column_config.TextColumn("notes", width="large"),
    }
    _st_dataframe(disp, width="stretch", hide_index=True, column_config=cfg)
    safe = re.sub(r"[^\w]+", "_", key_suffix).strip("_")[:40] or "anomalies"
    st.download_button(
        "Download anomalies (Excel)",
        data=export_excel(disp),
        file_name=f"troy_banks_anomalies_{safe}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_anom_{safe}"[:120],
    )


