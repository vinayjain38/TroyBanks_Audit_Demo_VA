"""
va_step2_anomalies_test.py

TEST VERSION: Uses in-memory pandas DataFrames with hardcoded test data
instead of reading from database. Same calculation & output logic.
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

# No database imports for test version

# -------------------------------------------------------------
# Configuration
# -------------------------------------------------------------
OUT_DIR = Path("data") / "interim" / "anomaly_test_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
# timestamp the test output to avoid locks and repeat runs
from datetime import datetime
suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_XLSX = OUT_DIR / f"va_step2_anomalies_TEST_{suffix}.xlsx"

CONFIG = {
    "YOY_SPIKE_THRESHOLD": 0.50,
    "ABS_SPIKE_THRESHOLD": 5.0 # Minimum daily kWh increase to care about
}

# ============================================================
# CREATE TEST DATA (replaces database)
# ============================================================
def create_test_data():
    """
    Creates realistic test DataFrame with:
    - 2 accounts (Account_A, Account_B)
    - 24 months of historical data (2023-2025)
    - Built-in anomalies in latest year (2025) for Account_A
    - Clean data for Account_B
    """
    test_records = []
    
    # Account A: Has anomalies in 2025
    account_a = "ACC-001"
    customer_a = "Test Building Complex A"
    
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            date = pd.Timestamp(year, month, 15)
            
            if year < 2025:
                # Historical baseline (2023-2024): stable consumption
                usage = 3000 + np.random.normal(0, 100)  # ~3000 kWh/month
                demand = 15 + np.random.normal(0, 0.5)   # ~15 kW peak
                billing_days = 30
            else:
                # 2025: introduce spikes in certain months
                if month in [3, 6, 9]:
                    # Spike months: 80% increase
                    usage = 3000 * 1.8 + np.random.normal(0, 100)  # ~5400 kWh/month
                    demand = 15 * 1.8 + np.random.normal(0, 0.5)   # ~27 kW peak
                else:
                    # Normal months
                    usage = 3000 + np.random.normal(0, 100)
                    demand = 15 + np.random.normal(0, 0.5)
                billing_days = 30
            
            charges = usage * 0.12  # $0.12 per kWh baseline
            
            test_records.append({
                "bill_from": date,
                "bill_to": date + pd.Timedelta(days=billing_days),
                "usage_kwh": max(usage, 0),
                "demand_kw": max(demand, 0),
                "charges": max(charges, 0),
                "account_number": account_a,
                "customer": customer_a,
                "billing_days": billing_days
            })
    
    # Account B: Clean data, no anomalies
    account_b = "ACC-002"
    customer_b = "Test Office Building B"
    
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            date = pd.Timestamp(year, month, 15)
            billing_days = 30
            
            # Consistent, predictable usage throughout
            usage = 1500 + np.random.normal(0, 50)  # ~1500 kWh/month
            demand = 8 + np.random.normal(0, 0.3)    # ~8 kW peak
            charges = usage * 0.12
            
            test_records.append({
                "bill_from": date,
                "bill_to": date + pd.Timedelta(days=billing_days),
                "usage_kwh": max(usage, 0),
                "demand_kw": max(demand, 0),
                "charges": max(charges, 0),
                "account_number": account_b,
                "customer": customer_b,
                "billing_days": billing_days
            })
    
    return pd.DataFrame(test_records)

# ============================================================
# CORE AUDIT LOGIC (same as main script)
# ============================================================
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

    # additional metrics requested by user
    # load factor: consumption relative to demand capacity
    df['Load_Factor'] = np.where(
        df['Demand'] > 0,
        df['Total Consumption'] / (df['Demand'] * df['Billing Days'] * 24),
        np.nan
    )

    # demand threshold / rate upgrade eligibility (3‑month rolling)
    df['Met_Threshold'] = df['Demand'] >= 50  # hardcoded threshold for tests
    df['Rolling_3Mo_Demand'] = df['Met_Threshold'].rolling(window=3, min_periods=3).sum()
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

# ============================================================
# HELPER FUNCTIONS (same as main script)
# ============================================================
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

# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    print("===== STEP 2: VA Anomalies (TEST VERSION with In-Memory Data) =====\n")

    # Load test data instead of database
    print("[INFO] Creating test data...")
    df = create_test_data()
    print(f"[INFO] Created {len(df)} test records for 2 accounts across 24 months\n")
    
    # Display test data summary
    print("[TEST DATA SUMMARY]")
    print(f"  Accounts: {df['account_number'].unique().tolist()}")
    print(f"  Date range: {df['bill_to'].min().date()} to {df['bill_to'].max().date()}")
    print(f"  Total records: {len(df)}\n")

    # Safety & Account Checks
    unique_accounts = df["account_number"].nunique()
    print(f"[INFO] Data loaded for {unique_accounts} distinct account(s).")
    if unique_accounts > 1:
        print("[INFO] Multiple accounts detected. GroupBy logic will safely isolate them.\n")

    # Null Handling Rules
    initial_rows = len(df)
    df = df.dropna(subset=['usage_kwh', 'bill_to'])
    df = df[df["usage_kwh"] > 0].copy()
    dropped_rows = initial_rows - len(df)
    if dropped_rows > 0:
        print(f"[INFO] Dropped {dropped_rows} rows due to 0 or missing Usage/Dates.")

    # Prepare for Audit Function
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
    audit_df = audit_df.rename(columns={"Account_ID": "account_number", "Bill To": "bill_period_end"})

    # Filter for the "Most Recent 12 Months" per account
    audit_df['Max_Date'] = audit_df.groupby('account_number')['bill_period_end'].transform('max')
    recent_12_months_mask = audit_df['bill_period_end'] >= (audit_df['Max_Date'] - pd.Timedelta(days=365))
    recent_df = audit_df[recent_12_months_mask].copy()

    print(f"[INFO] Filtered to most recent 12 months: {len(recent_df)} records")

    # Isolate Anomalies and Output
    anomalies_df = recent_df[recent_df["Is_Usage_Anomaly"] | recent_df["Is_New_Activation"]].copy()

    col_order = [
        "account_number", "customer", "bill_period_end", 
        "Total Consumption", "Demand", "Total Charges", "Effective_Cost_per_kWh",     
        "Load_Factor","Eligible_For_Rate_Upgrade","Is_Usage_Anomaly", "Is_New_Activation", "Anomaly_Reason"
    ]

    if anomalies_df.empty:
        print("\n[INFO] No anomalies detected in the most recent 12 months.")
        anomalies_df = pd.DataFrame(columns=col_order)
    else:
        print(f"\n[INFO] Found {len(anomalies_df)} anomaly rows in the most recent 12 months.")
        anomalies_df = anomalies_df[col_order]
        # Rename final columns for clean Excel presentation
        anomalies_df = anomalies_df.rename(columns={
            "Total Consumption": "usage_kwh", 
            "Demand": "demand_kw", 
            "Total Charges": "charges"
        })
        anomalies_df = anomalies_df.sort_values(["account_number", "bill_period_end"])

        # format currency columns by adding '$' prefix
        money_cols = [c for c in anomalies_df.columns if "charge" in c.lower() or "cost" in c.lower()]
        for col in money_cols:
            anomalies_df[col] = anomalies_df[col].apply(lambda v: f"${v:,.2f}" if pd.notna(v) else "")

    # Write Excel
    # remove existing output if it's locked from previous run
    if OUT_XLSX.exists():
        try:
            OUT_XLSX.unlink()
        except Exception:
            pass

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
            
        print(f"\n[SUCCESS] WROTE: {OUT_XLSX}")
        print(f"\n[OUTPUT SUMMARY]")
        print(f"  Anomaly rows: {len(anomalies_df)}")
        print(f"  Unique accounts with flags: {anomalies_df['account_number'].nunique() if len(anomalies_df) > 0 else 0}")
        
        if not anomalies_df.empty:
            print(f"\n[ANOMALIES DETECTED]")
            for _, row in anomalies_df.iterrows():
                reason = "Usage Spike" if row["Is_Usage_Anomaly"] else "New Activation"
                print(f"  {row['account_number']} ({row['customer']}) - {row['bill_period_end'].date()} - {reason}")
        
    except Exception as e:
        print(f"[ERROR] writing output: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
