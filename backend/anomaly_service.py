"""Anomaly pipeline matching streamlit build_usage_anomalies_df (without Streamlit dependency)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.va_step2_anomalies_db import process_troybanks_audit_data


def _strip_total_and_parse_dates(df: pd.DataFrame) -> pd.DataFrame:
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


def filter_anomalies_to_period(anomalies_df: pd.DataFrame, period_df: pd.DataFrame) -> pd.DataFrame:
    if anomalies_df.empty or period_df is None or period_df.empty:
        return anomalies_df.iloc[0:0].copy()
    pe = _strip_total_and_parse_dates(period_df)
    if pe.empty:
        return anomalies_df.iloc[0:0].copy()
    dmin, dmax = pe["bill_period_end"].min(), pe["bill_period_end"].max()
    ad = pd.to_datetime(anomalies_df["bill_period_end"], errors="coerce")
    return anomalies_df[(ad >= dmin) & (ad <= dmax)].copy()


def build_usage_anomalies_df(
    usage_df: pd.DataFrame,
    *,
    pct_spike_limit: float = 0.50,
    abs_spike_limit: float = 5.0,
    billing_median_multiplier: float = 2.5,
    billing_min_delta_cpk: float = 0.05,
    billing_min_kwh: float = 30.0,
    charge_median_multiplier: float = 2.5,
    charge_min_usd: float = 100.0,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = _strip_total_and_parse_dates(usage_df)
    if df.empty:
        return pd.DataFrame()

    for col in ("usage_kwh", "charges"):
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "demand_kw" not in df.columns:
        df["demand_kw"] = 0.0
    else:
        df["demand_kw"] = pd.to_numeric(df["demand_kw"], errors="coerce").fillna(0.0)

    df = df.dropna(subset=["usage_kwh"])
    df = df[df["usage_kwh"] >= 0].copy()
    if df.empty:
        return pd.DataFrame()

    if "contract_account" in df.columns:
        df["Account_ID"] = df["contract_account"].astype(str)
    elif "account_number" in df.columns:
        df["Account_ID"] = df["account_number"].astype(str)
    else:
        df["Account_ID"] = "Single_Account"

    df = df.sort_values(["Account_ID", "bill_period_end"]).reset_index(drop=True)
    df["billing_days"] = df.groupby("Account_ID", group_keys=False)["bill_period_end"].transform(
        _billing_days_by_account
    )

    audit_in = df.rename(
        columns={
            "bill_period_end": "Bill To",
            "billing_days": "Billing Days",
            "usage_kwh": "Total Consumption",
            "demand_kw": "Demand",
            "charges": "Total Charges",
        }
    )[
        ["Bill To", "Billing Days", "Total Consumption", "Demand", "Total Charges", "Account_ID"]
    ].copy()

    processed = process_troybanks_audit_data(
        audit_in,
        pct_spike_limit=pct_spike_limit,
        abs_spike_limit=abs_spike_limit,
    )

    tc = pd.to_numeric(processed["Total Consumption"], errors="coerce")
    tch = pd.to_numeric(processed["Total Charges"], errors="coerce")
    processed["_cpk"] = np.where(tc > 0, tch / tc, np.nan)
    med_cpk = processed.groupby("Account_ID")["_cpk"].transform("median")
    processed["_median_cpk"] = med_cpk
    processed["Is_Billing_Anomaly"] = (
        (tc >= billing_min_kwh)
        & med_cpk.notna()
        & (med_cpk > 0)
        & (processed["_cpk"] > (med_cpk * billing_median_multiplier))
        & (processed["_cpk"] > med_cpk + billing_min_delta_cpk)
    )

    med_chg = processed.groupby("Account_ID")["Total Charges"].transform("median")
    processed["_median_charge"] = med_chg
    processed["Is_Charge_Anomaly"] = (
        (tch >= charge_min_usd)
        & med_chg.notna()
        & (med_chg > 0)
        & (tch > charge_median_multiplier * med_chg)
    )

    def _compose_reason(row: pd.Series) -> str:
        parts = []
        base = str(row.get("Anomaly_Reason") or "").strip()
        if base:
            parts.append(base)
        if row.get("Is_Billing_Anomaly", False):
            cpk = row["_cpk"]
            med = row["_median_cpk"]
            parts.append(f"Billing: ${cpk:.4f}/kWh vs typical median ${med:.4f}/kWh for this account.")
        if row.get("Is_Charge_Anomaly", False):
            try:
                tcv = float(row["Total Charges"])
                mcv = float(row["_median_charge"])
                parts.append(f"Charge: ${tcv:,.2f} vs typical median bill ${mcv:,.2f}.")
            except (TypeError, ValueError):
                parts.append("Charge: unusually high vs typical median bill for this account.")
        return " ".join(parts).strip()

    processed["Display_Reason"] = processed.apply(_compose_reason, axis=1)
    mask = (
        processed["Is_Usage_Anomaly"]
        | processed["Is_New_Activation"]
        | processed["Is_Billing_Anomaly"]
        | processed["Is_Charge_Anomaly"]
    )
    flagged = processed.loc[mask].copy()
    if flagged.empty:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "bill_period_end": pd.to_datetime(flagged["Bill To"]).dt.strftime("%Y-%m-%d"),
            "account": flagged["Account_ID"].astype(str),
            "usage_kwh": flagged["Total Consumption"],
            "charges": flagged["Total Charges"],
            "$/kWh": pd.to_numeric(flagged["_cpk"], errors="coerce").round(4),
            "usage_spike": flagged["Is_Usage_Anomaly"],
            "new_activation": flagged["Is_New_Activation"],
            "billing_outlier": flagged["Is_Billing_Anomaly"],
            "charge_spike": flagged["Is_Charge_Anomaly"],
            "notes": flagged["Display_Reason"],
        }
    )
    out = out.reset_index(drop=True)
    period = view_period_df if view_period_df is not None else usage_df
    out = filter_anomalies_to_period(out, period)
    if out.empty:
        return out
    if "bill_period_end" in out.columns:
        out["bill_period_end"] = pd.to_datetime(out["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out
