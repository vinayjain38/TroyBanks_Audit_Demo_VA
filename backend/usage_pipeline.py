"""Build usage DataFrame from pivoted bill extract + profile (mirrors streamlit pivoted_to_usage_df)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _parse_money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip(),
        errors="coerce",
    ).fillna(0.0)


def _parse_money_coalesce(df: pd.DataFrame, col_names: list[str]) -> pd.Series:
    """Parse money columns and coalesce left-to-right (NaN/blank only). OCR often fills * Subtotal but not ** Total Charges."""
    out: pd.Series | None = None
    for name in col_names:
        if name not in df.columns:
            continue
        part = pd.to_numeric(
            df[name].astype(str).str.replace(r"[\$,]", "", regex=True).str.strip(),
            errors="coerce",
        )
        if out is None:
            out = part
        else:
            out = out.fillna(part)
    if out is None:
        return pd.Series(0.0, index=df.index)
    return out.fillna(0.0)


def pivoted_to_usage_df(pivoted: pd.DataFrame, profile: dict) -> pd.DataFrame:
    df = pivoted.copy()
    customer = profile.get("Account Profile", "Unknown")
    if "contract_account" in df.columns:
        non_null = df["contract_account"].dropna().astype(str)
        contract_acct = non_null.iloc[0] if not non_null.empty else profile.get("ACCOUNT NO.", "Unknown")
    else:
        contract_acct = str(profile.get("ACCOUNT NO.", "Unknown")).strip()

    if "Bill To" in df.columns:
        df["bill_period_end"] = pd.to_datetime(df["Bill To"], format="%m/%d/%y", errors="coerce")
    elif "Year" in df.columns and "Month" in df.columns:
        _mm = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
               "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
        df["_m"] = df["Month"].str.upper().str[:3].map(_mm)
        df["bill_period_end"] = pd.to_datetime(
            df["Year"].astype(str) + "-" + df["_m"].astype(str) + "-28", errors="coerce"
        )
        df.drop(columns=["_m"], inplace=True)

    usage_col = next((c for c in ["Total Consumption", "total_consumption"] if c in df.columns), None)
    df["usage_kwh"] = pd.to_numeric(df[usage_col], errors="coerce").fillna(0) if usage_col else 0.0

    df["charges"] = _parse_money_coalesce(
        df,
        ["** Total Charges", "* Subtotal", "Total Charges"],
    )

    if "Billed Rate" in df.columns:
        df["current_rate"] = df["Billed Rate"].fillna(profile.get("Current Rate", "Unknown"))
    else:
        df["current_rate"] = profile.get("Current Rate", "Unknown")

    if "Demand" in df.columns:
        df["demand_kw"] = pd.to_numeric(df["Demand"], errors="coerce").fillna(0.0)
    else:
        df["demand_kw"] = 0.0
    df["bill_month"] = pd.DatetimeIndex(df["bill_period_end"]).to_period("M").astype(str)
    df["customer"] = customer
    df["contract_account"] = str(contract_acct).strip()
    df["rate_code_norm"] = df["current_rate"].astype(str).str.upper().str.strip()
    df["address_suppl"] = profile.get("Service Address", "")
    df["addr_suppl_norm"] = df["address_suppl"].str.upper().str.strip()
    df["street"] = df["city"] = df["state"] = df["zip"] = ""

    df = df.dropna(subset=["bill_period_end"])
    df = df[df["usage_kwh"] > 0]

    final_cols = ["contract_account", "customer", "current_rate", "rate_code_norm",
                  "address_suppl", "addr_suppl_norm", "street", "city", "state", "zip",
                  "bill_month", "bill_period_end", "usage_kwh", "demand_kw", "charges"]
    return df[[c for c in final_cols if c in df.columns]].reset_index(drop=True)


def records_to_usage_df(records: list[dict]) -> pd.DataFrame:
    """Normalize API JSON usage rows into a DataFrame for schedule functions.

    Mirrors ``pivoted_to_usage_df`` enough that schedule_* logic matches the monolith:
    valid bill dates, numeric usage/charges/demand, stripped ``current_rate`` / ``contract_account``,
    chronological order (needed for VE-102 unmetered window), and non-positive usage dropped.
    """
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "bill_period_end" in df.columns:
        df["bill_period_end"] = pd.to_datetime(df["bill_period_end"], errors="coerce")
    df = df.dropna(subset=["bill_period_end"])
    for col in ("usage_kwh", "charges", "demand_kw"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["usage_kwh"] = df["usage_kwh"].fillna(0.0)
    df["charges"] = df["charges"].fillna(0.0)
    df["demand_kw"] = df["demand_kw"].fillna(0.0)

    def _clean_str(series: pd.Series) -> pd.Series:
        return series.map(lambda x: "" if pd.isna(x) else str(x).strip())

    if "current_rate" in df.columns:
        df["current_rate"] = _clean_str(df["current_rate"])
    else:
        df["current_rate"] = ""
    if "contract_account" in df.columns:
        df["contract_account"] = _clean_str(df["contract_account"])
    else:
        df["contract_account"] = ""
    df = df[df["usage_kwh"] > 0]
    df = df.sort_values("bill_period_end").reset_index(drop=True)
    return df
