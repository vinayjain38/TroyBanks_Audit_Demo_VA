# step1_va_load_normalize.py
# STEP 1 (Virginia): Load + normalize + export billing base table

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

DATA_DIR = os.path.join(os.getcwd(), "data")

CONFIG = {
    "CUSTOMER_WORKBOOK": os.path.join(DATA_DIR, "City of VA Beach Usage History.xlsb"),
    "EXPORT_SHEET": "Export",
    "DATA_SHEET": "Data",

    "OUT_BASE": os.path.join(DATA_DIR, "va_step1_base_new.xlsx"),
}

# ============================================================
# HELPERS
# ============================================================

def norm(s):
    if pd.isna(s):
        return ""
    return str(s).strip()


def parse_yyyymmdd(x):
    """Parses Excel serial dates, timestamps, or YYYYMMDD strings."""
    if pd.isna(x):
        return pd.NaT

    # Excel serial (30k–60k days range)
    if isinstance(x, (int, float)) and 20000 <= float(x) <= 60000:
        return pd.to_datetime(float(x), unit="D", origin="1899-12-30", errors="coerce")

    # Datetime already
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return pd.to_datetime(x, errors="coerce")

    # String formats
    s = str(x).strip()
    if not s:
        return pd.NaT

    dt = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    if pd.isna(dt):
        dt = pd.to_datetime(s, errors="coerce")

    return dt


def safe_to_numeric(x):
    return pd.to_numeric(x, errors="coerce")


# ============================================================
# MAIN
# ============================================================

def main():
    print("===== STEP 1: VA Load + Normalize =====")

    # ---------------- LOAD ----------------
    try:
        exp = pd.read_excel(
            CONFIG["CUSTOMER_WORKBOOK"],
            sheet_name=CONFIG["EXPORT_SHEET"],
            engine="pyxlsb",
        )
        dat = pd.read_excel(
            CONFIG["CUSTOMER_WORKBOOK"],
            sheet_name=CONFIG["DATA_SHEET"],
            engine="pyxlsb",
        )
    except Exception as e:
        print("❌ ERROR reading XLSB:", e)
        sys.exit(1)

    # ---------------- STANDARDIZE COLUMNS ----------------
    exp_map = {
        "Customer": "customer",
        "Contract Account": "contract_account",
        "Rate": "current_rate",
        "Address Suppl.": "address_suppl",
        "Street": "street",
        "Street No.": "street_no",
        "City": "city",
        "State": "state",
        "Zip": "zip",
        "Meter #": "meter_no",
        "Billing Address": "billing_address",
    }

    dat_map = {
        "CONTRACT_ACCOUNT": "contract_account",
        "BILL_PERIOD_END": "bill_period_end",
        "USAGE (kWh)": "usage_kwh",
        "DEMAND (KW)": "demand_kw",
        "CHARGES": "charges",
        "POSTING_DATE": "posting_date",
        "RATE": "rate_from_data",
        "INVOICE": "invoice",
        "ADDRESS": "service_address",
    }

    exp.rename(columns=exp_map, inplace=True)
    dat.rename(columns=dat_map, inplace=True)

    # ---------------- CLEAN FORMATS ----------------
    dat["bill_period_end"] = dat["bill_period_end"].apply(parse_yyyymmdd)
    dat["usage_kwh"] = safe_to_numeric(dat["usage_kwh"])
    dat["demand_kw"] = safe_to_numeric(dat["demand_kw"])
    dat["charges"] = safe_to_numeric(dat["charges"])

    dat["bill_month"] = dat["bill_period_end"].dt.to_period("M").astype(str)

    # ---------------- NORMALIZE RATE CODES ----------------
    exp["rate_code_norm"] = (
        exp["current_rate"]
        .astype(str)
        .str.upper()
        .str.strip()
        .replace("", np.nan)
    )

    # ---------------- NORMALIZE ADDRESS ----------------
    if "address_suppl" in exp.columns:
        addr = exp["address_suppl"].apply(lambda x: norm(x).upper())
        addr = addr.str.replace(r"\s+", " ", regex=True).str.strip()
        exp["addr_suppl_norm"] = addr.replace("", np.nan)
    else:
        exp["addr_suppl_norm"] = np.nan

    # ---------------- KEEP ONLY VIRGINIA ACCOUNTS ----------------
    mask = exp["state"].astype(str).str.upper().isin(["VA", "VIRGINIA"])
    exp = exp[mask].copy()

    # ---------------- MERGE BILLING + CUSTOMER ATTRIBUTES ----------------
    base = dat.merge(
        exp[
            [
                "contract_account",
                "customer",
                "current_rate",
                "rate_code_norm",
                "address_suppl",
                "addr_suppl_norm",
                "street",
                "city",
                "state",
                "zip",
            ]
        ],
        how="left",
        on="contract_account",
    )

    base = base.sort_values(["contract_account", "bill_period_end"])

    # ---------------- GAP DAYS ----------------
    base["GAP_DAYS_FROM_PREV"] = (
        base.groupby("contract_account")["bill_period_end"]
            .diff()
            .dt.days
    )

    # ---------------- FINAL COLUMN ORDER ----------------
    final_cols = [
        "contract_account",
        "customer",
        "current_rate",
        "rate_code_norm",
        "address_suppl",
        "addr_suppl_norm",
        "street",
        "city",
        "state",
        "zip",
        "bill_month",
        "bill_period_end",
        "GAP_DAYS_FROM_PREV",
        "usage_kwh",
        "demand_kw",
        "charges",
    ]

    base = base[final_cols]

    # ---------------- SAVE OUTPUT ----------------
    try:
        base.to_excel(CONFIG["OUT_BASE"], index=False)
        print("✅ WROTE:", CONFIG["OUT_BASE"])
    except Exception as e:
        print("❌ ERROR saving Step1 output:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
