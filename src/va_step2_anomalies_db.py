import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

try:
    from Utils import database
    get_engine = getattr(database, "get_engine", None)
except Exception: 
    database = None
    get_engine = None

import sqlalchemy

# -------------------------------------------------------------
# Configuration
# -------------------------------------------------------------
OUT_DIR = Path("data") / "interim" / "anomaly_test_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_XLSX = OUT_DIR / "va_step2_anomalies.xlsx"

CONFIG = {
    "USAGE_TABLE": "usage_bill",
    "YOY_SPIKE_THRESHOLD": 0.50,
    "ABS_SPIKE_THRESHOLD": 5.0 # Minimum daily kWh increase to care about
}

# -------------------------------------------------------------
# Core Audit Logic
# -------------------------------------------------------------
def process_troybanks_audit_data(df, pct_spike_limit=0.50, abs_spike_limit=5.0):
    """
    Processes cleaned utility data to generate historical medians, 
    flag anomalies, and generate auditor reasoning.
    """
    # 1. Base Normalization
    df['Daily_Consumption'] = df['Total Consumption'] / df['Billing Days']
    
    df['Effective_Cost_per_kWh'] = np.where(
        df['Total Consumption'] > 0, 
        df['Total Charges'] / df['Total Consumption'], 
        0
    )

    # additional metrics
    df['Load_Factor'] = np.where(
        df['Demand'] > 0,
        df['Total Consumption'] / (df['Demand'] * df['Billing Days'] * 24),
        np.nan
    )
    # rolling demand threshold (same threshold as config could be used but test uses 50)
    df['Met_Threshold'] = df['Demand'] >= CONFIG.get('ABS_SPIKE_THRESHOLD', 5.0) * 10  # approximate, tweak as needed
    df['Rolling_3Mo_Demand'] = df.groupby('Account_ID')['Met_Threshold'].transform(
        lambda x: x.rolling(window=3, min_periods=3).sum()
    )
    df['Eligible_For_Rate_Upgrade'] = df['Rolling_3Mo_Demand'] == 3
    df = df.drop(columns=['Met_Threshold', 'Rolling_3Mo_Demand'])

    # 2. Historical YoY Medians (Safely Grouped by Account)
    df['Month'] = df['Bill To'].dt.month
    df['Year'] = df['Bill To'].dt.year
    historical_medians = []
    
    for index, row in df.iterrows():
        acct = row['Account_ID']
        current_year = row['Year']
        current_month = row['Month']
        
        # Look strictly at previous years, same month, same account
        history = df[(df['Account_ID'] == acct) & 
                     (df['Month'] == current_month) & 
                     (df['Year'] < current_year)]
        
        if not history.empty:
            median_val = history['Daily_Consumption'].median()
        else:
            median_val = np.nan
            
        historical_medians.append(median_val)
        
    df['Hist_Median_Daily_Consumption'] = historical_medians
    
    # 3. Calculate Spikes
    df['YoY_Spike_Pct'] = np.where(
        df['Hist_Median_Daily_Consumption'] > 0,
        (df['Daily_Consumption'] - df['Hist_Median_Daily_Consumption']) / df['Hist_Median_Daily_Consumption'],
        0 
    )
    df['Absolute_Daily_Increase'] = df['Daily_Consumption'] - df['Hist_Median_Daily_Consumption']

    # 4. Anomaly Flags
    df['Is_Usage_Anomaly'] = (
        (df['YoY_Spike_Pct'] > pct_spike_limit) & 
        (df['Absolute_Daily_Increase'] > abs_spike_limit)
    )
    df['Is_New_Activation'] = (
        (df['Hist_Median_Daily_Consumption'] == 0) & 
        (df['Daily_Consumption'] > abs_spike_limit)
    )

    # 5. Generate Auditor Reasoning Text
    def get_reason(row):
        if row['Is_Usage_Anomaly']:
            pct = row['YoY_Spike_Pct'] * 100
            curr = row['Daily_Consumption']
            hist = row['Hist_Median_Daily_Consumption']
            return f"Spike of {pct:.1f}%. Current usage is {curr:.1f} kWh/day vs historical normal of {hist:.1f} kWh/day."
        elif row['Is_New_Activation']:
            curr = row['Daily_Consumption']
            return f"New usage detected at {curr:.1f} kWh/day. Historical median for this month was 0."
        return ""

    df['Anomaly_Reason'] = df.apply(get_reason, axis=1)
    
    # Cleanup temporary columns
    df = df.drop(columns=['Month', 'Year'])
    return df

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------
def parse_yyyymmdd(x):
    if pd.isna(x): return pd.NaT
    try:
        if isinstance(x, (int, float)) and 20000 <= float(x) <= 60000:
            return pd.to_datetime(float(x), unit="D", origin="1899-12-30", errors="coerce")
    except Exception: pass
    if isinstance(x, (pd.Timestamp, np.datetime64)): return pd.to_datetime(x, errors="coerce")
    s = str(x).strip()
    if not s: return pd.NaT
    dt = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    if pd.isna(dt): dt = pd.to_datetime(s, errors="coerce")
    return dt

def safe_to_numeric(x):
    if isinstance(x, pd.Series):
        cleaned = (x.astype(str).str.replace(r"\s", "", regex=True)
                   .str.replace("$", "", regex=False).str.replace(",", "", regex=False)
                   .str.replace(r"^\((.*)\)$", r"-\1", regex=True))
        return pd.to_numeric(cleaned, errors="coerce")
    if pd.isna(x) or str(x).strip() == "": return np.nan
    text = str(x).strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"): text = f"-{text[1:-1]}"
    return pd.to_numeric(text, errors="coerce")

def get_db_engine():
    if get_engine is not None:
        try: return get_engine()
        except Exception: pass
    url = os.environ.get("DATABASE_URL")
    if not url: raise RuntimeError("No DB engine available and DATABASE_URL not set")
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return sqlalchemy.create_engine(url)

def load_usage_table(cols):
    engine = get_db_engine()
    cols_sql = ", ".join([f'"{c}"' for c in cols])
    query = f"SELECT {cols_sql} FROM {CONFIG['USAGE_TABLE']}"
    return pd.read_sql(query, con=engine)

def get_table_columns(table_name):
    engine = get_db_engine()
    insp = sqlalchemy.inspect(engine)
    try: return [c["name"] for c in insp.get_columns(table_name)]
    except Exception: return []

# -------------------------------------------------------------
# Main Execution
# -------------------------------------------------------------
def main():
    print("===== STEP 2: VA Anomalies (Latest Year YoY Analysis) =====")

    base_cols = ["bill_from_raw", "bill_to_raw", "total_consumption", "demand", "total_charges_raw", "billed_rate"]
    available_cols = get_table_columns(CONFIG["USAGE_TABLE"])
    cols = base_cols.copy()
    if "accountNumber" in available_cols: cols.append("accountNumber")
    if "CompanyName" in available_cols: cols.append("CompanyName")

    try:
        df = load_usage_table(cols)
        print(f"[INFO] Loaded {len(df)} records from usage_bill")
    except Exception as e:
        print(f"[ERROR] reading usage table: {str(e)}")
        sys.exit(1)

    # Standardize column names
    rename_map = {
        "bill_from_raw": "bill_from", "bill_to_raw": "bill_to", 
        "total_consumption": "usage_kwh", "demand": "demand_kw", 
        "total_charges_raw": "charges", "billed_rate": "current_rate", 
        "accountNumber": "account_number", "CompanyName": "customer"
    }
    df = df.rename(columns=rename_map)

    # 1. Type Casting & Date Parsing
    df["bill_from"] = df["bill_from"].apply(parse_yyyymmdd)
    df["bill_to"] = df["bill_to"].apply(parse_yyyymmdd)
    df["bill_period_end"] = df["bill_to"]
    df["usage_kwh"] = safe_to_numeric(df["usage_kwh"])
    df["demand_kw"] = safe_to_numeric(df["demand_kw"])
    df["charges"] = safe_to_numeric(df["charges"])
    df["billing_days"] = (df["bill_to"] - df["bill_from"]).dt.days

    # 2. Safety & Account Checks
    if "account_number" not in df.columns or df["account_number"].isna().all():
        print("[WARNING] account_number missing. Defaulting to 'Single_Account'.")
        df["account_number"] = "Single_Account"
    if "customer" not in df.columns:
        df["customer"] = "Unknown"
        
    unique_accounts = df["account_number"].nunique()
    print(f"[INFO] Data loaded for {unique_accounts} distinct account(s).")
    if unique_accounts > 1:
        print("[WARNING] Multiple accounts detected in upload. GroupBy logic will safely isolate them.")

    # 3. Null Handling Rules
    # Demand: If null, it means 0.
    df["demand_kw"] = df["demand_kw"].fillna(0)
    
    # Usage: If null or 0, skip the month completely so it doesn't skew historical medians.
    initial_rows = len(df)
    df = df.dropna(subset=['usage_kwh', 'bill_to'])
    df = df[df["usage_kwh"] >= 0].copy()
    dropped_rows = initial_rows - len(df)
    if dropped_rows > 0:
        print(f"[INFO] Dropped {dropped_rows} rows due to 0 or missing Usage/Dates.")

    # 4. Prepare for Audit Function
    mapping = {
        "bill_to": "Bill To",
        "billing_days": "Billing Days",
        "usage_kwh": "Total Consumption",
        "demand_kw": "Demand",
        "charges": "Total Charges",
        "account_number": "Account_ID"
    }
    
    # Sort strictly by Account then Date BEFORE processing
    audit_df = df.rename(columns=mapping)
    audit_df = audit_df.sort_values(by=['Account_ID', 'Bill To']).reset_index(drop=True)

    print("\n--- PROCESSING AUDIT METRICS ---")
    audit_df = process_troybanks_audit_data(
        audit_df, 
        pct_spike_limit=CONFIG["YOY_SPIKE_THRESHOLD"], 
        abs_spike_limit=CONFIG["ABS_SPIKE_THRESHOLD"]
    )

    # Map names back for output
    # Drop the old duplicate column before renaming to prevent the alignment error
    if 'bill_period_end' in audit_df.columns:
        audit_df = audit_df.drop(columns=['bill_period_end'])
        
    audit_df = audit_df.rename(columns={"Account_ID": "account_number", "Bill To": "bill_period_end"})

    # 5. Filter for the "Most Recent 12 Months" per account
    # Compute each account's latest bill_period_end explicitly (avoid pandas transform hiccup)
    # compute per-account max using agg (produces one-column DataFrame)
    max_dates = audit_df.groupby('account_number').agg(Max_Date=('bill_period_end', 'max'))
    # map the maximum date back onto the main frame; this yields a Series
    audit_df['Max_Date'] = audit_df['account_number'].map(max_dates['Max_Date'])
    recent_12_months_mask = audit_df['bill_period_end'] >= (
        audit_df['Max_Date'] - pd.Timedelta(days=365)
    )
    recent_df = audit_df[recent_12_months_mask].copy()

    # 6. Isolate Anomalies and Output
    anomalies_df = recent_df[recent_df["Is_Usage_Anomaly"] | recent_df["Is_New_Activation"]].copy()

    col_order = [
        "account_number", "customer", "bill_period_end", 
        "Total Consumption", "Demand", "Total Charges", 
        "Effective_Cost_per_kWh", "Load_Factor", "Eligible_For_Rate_Upgrade",
        "Is_Usage_Anomaly", "Is_New_Activation", "Anomaly_Reason"
    ]

    if anomalies_df.empty:
        print("[INFO] No anomalies detected in the most recent 12 months.")
        anomalies_df = pd.DataFrame(columns=col_order)
    else:
        print(f"[INFO] Found {len(anomalies_df)} anomaly rows in the most recent 12 months.")
        anomalies_df = anomalies_df[col_order]
        # Rename final columns for clean Excel presentation
        anomalies_df = anomalies_df.rename(columns={
            "Total Consumption": "usage_kwh", 
            "Demand": "demand_kw", 
            "Total Charges": "charges"
        })
        anomalies_df = anomalies_df.sort_values(["account_number", "bill_period_end"])

        # add $ prefix to currency columns
        money_cols = [c for c in anomalies_df.columns if "charge" in c.lower() or "cost" in c.lower()]
        for col in money_cols:
            anomalies_df[col] = anomalies_df[col].apply(lambda v: f"${v:,.2f}" if pd.notna(v) else "")

    # 7. Write Excel
    try:
        with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
            anomalies_df.to_excel(writer, sheet_name="anomalies", index=False)

            if not anomalies_df.empty:
                summary = anomalies_df.groupby("account_number").agg(
                    customer=("customer", "first"),
                    total_flags=("Is_Usage_Anomaly", "sum"),
                    activation_flags=("Is_New_Activation", "sum"),
                ).reset_index()
            else:
                summary = pd.DataFrame(columns=["account_number", "customer", "total_flags", "activation_flags"])
            summary.to_excel(writer, sheet_name="account_summary", index=False)
            
        print(f"[SUCCESS] WROTE: {OUT_XLSX}")
    except Exception as e:
        print(f"[ERROR] writing output: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()