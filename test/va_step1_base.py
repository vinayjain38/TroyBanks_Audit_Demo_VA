# step1_va_load_normalize.py
# STEP 1 (Virginia): Load + normalize + export billing base table

"""
File: va_step1_base.py

- Purpose: Load raw usage bill (City of VA Beach Usage History.xlsb), normalize and merge customer + billing rows, and write a clean base file (`va_step1_base_new.xlsx`) used by downstream code.

- Config: `CONFIG` defines input workbook (`CUSTOMER_WORKBOOK`), sheets (`EXPORT_SHEET`, `DATA_SHEET`) and output path (`OUT_BASE`).

- Main steps:
  - Load two sheets from the XLSB (`Export` → customer metadata, Data → billing rows) using `pyxlsb`.
  - Rename columns with `exp_map` / `dat_map` to canonical names (e.g., `Contract Account` → `contract_account`, `USAGE (kWh)` → `usage_kwh`).
  - Clean and parse fields:
    - `parse_yyyymmdd()` converts Excel serial dates, timestamps, or YYYYMMDD strings to pandas datetimes.
    - `safe_to_numeric()` coerces numeric columns (`usage_kwh`, `demand_kw`, `charges`).
  - Generate `bill_month` (period string) and compute `GAP_DAYS_FROM_PREV` — days since prior bill per account.
  - Normalize `current_rate` into `rate_code_norm` and clean address supplement into `addr_suppl_norm`.
  - Filter to Virginia accounts (state in `VA` / `VIRGINIA`).
  - Merge customer metadata into billing rows on `contract_account`.
  - Reorder to `final_cols` and write `CONFIG["OUT_BASE"]`.

- Key helper functions:
  - `norm(s)`: trim & blank-to-empty.
  - `parse_yyyymmdd(x)`: robust date parsing (handles Excel serials, timestamps, YYYYMMDD strings).
  - `safe_to_numeric(x)`: numeric coercion.

- Output: Excel file at `CONFIG["OUT_BASE"]` containing per-row billing with columns:
  - `contract_account`, `customer`, `current_rate`, `rate_code_norm`, address fields, `bill_month`, `bill_period_end`, `GAP_DAYS_FROM_PREV`, `usage_kwh`, `demand_kw`, `charges`.

- Assumptions & caveats:
  - Input workbook must be an XLSB readable by `pyxlsb`.
  - Column names in the XLSB must match mappings in `exp_map` / `dat_map`; otherwise add mappings.
  - Date parsing expects sensible serials or recognizable strings; unusual formats may parse to NaT and be dropped downstream.
  - Filtering to VA is intentional; remove that filter if you want nationwide rows.

  
- Suggestions:  
  - Add logging instead of prints for better diagnostics.  
  - Optionally write a CSV alongside XLSX for faster downstream reads.  
  - Add small unit tests for `parse_yyyymmdd()` with representative inputs.

Want me to add CSV export, logging, or a brief sample test for the date parser?
"""




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
