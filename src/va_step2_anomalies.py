# step2_va_anomalies.py
# STEP 2 (Virginia): Compute YoY anomalies + 12-month history + summary sheets

import os
import sys
import numpy as np
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

DATA_DIR = os.path.join(os.getcwd(), "data")

CONFIG = {
    "IN_BASE": os.path.join(DATA_DIR, "va_step1_base.xlsx"),
    "OUT_XLSX": os.path.join(DATA_DIR, "va_step2_anomalies.xlsx"),

    # Threshold: +50% YoY demand spike
    "YOY_SPIKE_THRESHOLD": 0.50,
}

# ============================================================
# HELPERS
# ============================================================

def safe_to_numeric(x):
    return pd.to_numeric(x, errors="coerce")


# ============================================================
# ADD YoY + 12M HISTORY
# ============================================================

def add_seasonality_yoy(df):
    df = df.copy()
    df["month_num"] = df["bill_period_end"].dt.month
    df["year"] = df["bill_period_end"].dt.year

    groups = []
    for acc, g in df.groupby("contract_account", sort=False):
        g = g.sort_values("bill_period_end").copy()

        g["YOY_USAGE_DELTA_PCT"] = np.nan
        g["YOY_DEMAND_DELTA_PCT"] = np.nan

        # Map: (year, month) → index
        idx_map = {
            (int(r["year"]), int(r["month_num"])): idx
            for idx, r in g[["year", "month_num"]].iterrows()
        }

        # Compute YoY deltas
        for idx, row in g.iterrows():
            prev_idx = idx_map.get((int(row["year"] - 1), int(row["month_num"])))
            if prev_idx is None:
                continue

            prev = g.loc[prev_idx]
            if pd.notna(prev["usage_kwh"]) and prev["usage_kwh"] > 0:
                g.at[idx, "YOY_USAGE_DELTA_PCT"] = \
                    (row["usage_kwh"] - prev["usage_kwh"]) / prev["usage_kwh"]

            if pd.notna(prev["demand_kw"]) and prev["demand_kw"] > 0:
                g.at[idx, "YOY_DEMAND_DELTA_PCT"] = \
                    (row["demand_kw"] - prev["demand_kw"]) / prev["demand_kw"]

        g["USAGE_SPIKE_YOY_FLAG"] = (
            g["YOY_USAGE_DELTA_PCT"] >= CONFIG["YOY_SPIKE_THRESHOLD"]
        )
        g["DEMAND_SPIKE_YOY_FLAG"] = (
            g["YOY_DEMAND_DELTA_PCT"] >= CONFIG["YOY_SPIKE_THRESHOLD"]
        )

        # ---- 12-MONTH HISTORY ----
        months = g["bill_period_end"].dt.to_period("M")
        uniq = pd.Series(months.unique()).sort_values()

        valid_months = set()
        start = 0
        for i in range(1, len(uniq) + 1):
            if i == len(uniq) or (uniq.iloc[i] - uniq.iloc[i-1]) != 1:
                if (i - start) >= 12:
                    for p in uniq.iloc[start:i]:
                        valid_months.add(p)
                start = i

        g["HAS_12M_HISTORY"] = months.isin(valid_months)
        groups.append(g)

    return pd.concat(groups, ignore_index=True)


# ============================================================
# ANOMALY REASONS
# ============================================================

def add_reasons(df):
    df = df.copy()
    reasons = []

    for row in df.itertuples(index=False):
        r = []

        if getattr(row, "DEMAND_SPIKE_YOY_FLAG", False):
            pct = getattr(row, "YOY_DEMAND_DELTA_PCT", np.nan)
            if pd.notna(pct):
                r.append(f"DEMAND YoY +{round(pct * 100, 1)}%")

        if getattr(row, "USAGE_SPIKE_YOY_FLAG", False):
            pct = getattr(row, "YOY_USAGE_DELTA_PCT", np.nan)
            if pd.notna(pct):
                r.append(f"USAGE YoY +{round(pct * 100, 1)}% (info)")

        reasons.append("; ".join(r))

    df["ANOMALY_REASON"] = reasons
    df["ANOMALY_FOR_REVIEW"] = df["DEMAND_SPIKE_YOY_FLAG"].astype(bool)

    return df


# ============================================================
# MAIN
# ============================================================

def main():
    print("===== STEP 2: VA Anomalies =====")

    # ---- Load Step1 output ----
    try:
        df = pd.read_excel(CONFIG["IN_BASE"])
    except Exception as e:
        print("❌ ERROR reading Step1 output:", e)
        sys.exit(1)

    df["bill_period_end"] = pd.to_datetime(df["bill_period_end"], errors="coerce")
    df["usage_kwh"] = safe_to_numeric(df["usage_kwh"])
    df["demand_kw"] = safe_to_numeric(df["demand_kw"])
    df["charges"] = safe_to_numeric(df["charges"])

    df = df.sort_values(["contract_account", "bill_period_end"]).copy()

    # ---- add YoY + history ----
    df = add_seasonality_yoy(df)

    # ---- add anomaly reasons ----
    df = add_reasons(df)

    # ---- monthly anomalies sheet ----
    cols = [
        "contract_account", "customer", "current_rate", "rate_code_norm",
        "address_suppl", "addr_suppl_norm", "city", "state", "zip",
        "bill_month", "bill_period_end",
        "usage_kwh", "demand_kw", "charges",
        "GAP_DAYS_FROM_PREV",
        "HAS_12M_HISTORY",
        "YOY_USAGE_DELTA_PCT", "YOY_DEMAND_DELTA_PCT",
        "USAGE_SPIKE_YOY_FLAG", "DEMAND_SPIKE_YOY_FLAG",
        "ANOMALY_FOR_REVIEW", "ANOMALY_REASON",
    ]

    for c in cols:
        if c not in df.columns:
            df[c] = np.nan

    monthly_anoms = df[cols]

    # ---- account summary sheet ----
    acct = df.groupby("contract_account").agg(
        customer=("customer", "first"),
        current_rate=("current_rate", "first"),
        rate_code_norm=("rate_code_norm", "first"),
        bills=("bill_period_end", "count"),
        max_gap_days=("GAP_DAYS_FROM_PREV", "max"),
        has_12m_history=("HAS_12M_HISTORY", "max"),
        yoy_demand_spike_any=("DEMAND_SPIKE_YOY_FLAG", "any"),
        yoy_usage_spike_any=("USAGE_SPIKE_YOY_FLAG", "any"),
        any_anomaly_for_review=("ANOMALY_FOR_REVIEW", "any"),
    ).reset_index()

    # ---- WRITE OUTPUT ----
    with pd.ExcelWriter(CONFIG["OUT_XLSX"], engine="openpyxl") as writer:
        monthly_anoms.to_excel(writer, sheet_name="monthly_anoms", index=False)
        acct.to_excel(writer, sheet_name="account_summary", index=False)

    print("✅ WROTE:", CONFIG["OUT_XLSX"])


if __name__ == "__main__":
    main()
