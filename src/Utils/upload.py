import pandas as pd
import argparse
import sys
from pathlib import Path
from src.Utils.database import engine
from sqlalchemy import text
import datetime
from src.Utils.db_upsert import upsert_dataframe

# ==========================================
# CONFIGURATION: COLUMN MAPPINGS
# ==========================================
# This tells Python: "When you see '* Subtotal' in Excel, put it in 'subtotal_raw' in DB"

USAGE_MAPPING = {
    
    "Year": "year",
    "Month": "month",
    "* Subtotal": "subtotal_raw",
    "** Total Charges": "total_charges_raw",
    "Bill From": "bill_from_raw",
    "Bill To": "bill_to_raw",
    "Billing Days": "billing_days",
    "Billed Rate": "billed_rate",
    "Bill Summary": "bill_summary",
    "Demand": "demand",
    "Demand Charges": "demand_charges",
    "Demand ESS": "demand_ess",
    "Distribution Demand": "distribution_demand",
    "Distribution Demand Sec.": "distribution_demand_sec",
    "RKVA": "rkva",
    "Total Consumption": "total_consumption",
    "Historical Electricity Usage": "historical_usage",
    "Energy Charges": "energy_charges",
    "Energy DIS": "energy_dis",
    "Energy ESS": "energy_ess",
    "Fuel Charges": "fuel_charges",
    "Fuel Chg": "fuel_chg_abbr",
    "Basic Cust. Charges": "basic_cust_charges",
    "Basic Customer Chg": "basic_cust_chg_abbr",
    "Off Peak Energy ESS": "off_peak_energy_ess",
    "Off Peak Usage": "off_peak_usage",
    "On Peak Energy ESS": "on_peak_energy_ess",
    "On Peak Usage": "on_peak_usage",
    "Virginia Tax Surcharge": "tax_surcharge",
    "Transmission Demand": "transmission_demand",
    "Transmission Energy": "transmission_energy",
    "Other Charges/Credits": "other_charges_credits",
    "kW Adj ESS Secondary": "kw_adj_ess_secondary",
    "W": "w_misc",
    "�": "unknown_symbol",
    "PITTSYLVANIA CNTY SRVC AUTH |": "service_auth_name",
    # occasionally the pivoted sheet might already carry customer/account info
    "Account Number": "accountNumber",
    "ACCOUNT NO." : "accountNumber",
    "Customer Name": "CompanyName",
    "Account Profile": "CompanyName",
    # Riders: Parser normalizes all casing variants to canonical form (kW / kWh)
    # so only canonical keys needed here
    "Rider B kW": "rider_b_kw",
    "Rider B kWh": "rider_b_kwh",
    "Rider BW kW": "rider_bw_kw",
    "Rider BW kWh": "rider_bw_kwh",
    "Rider CCR": "rider_ccr",
    "Rider CE kW": "rider_ce_kw",
    "Rider CE kWh": "rider_ce_kwh",
    "Rider DIST kW": "rider_dist_kw",
    "Rider DIST kWh": "rider_dist_kwh",
    "Rider E kW": "rider_e_kw",
    "Rider E kWh": "rider_e_kwh",
    "Rider GEN kW": "rider_gen_kw",
    "Rider GEN kWh": "rider_gen_kwh",
    "Rider GT kW": "rider_gt_kw",
    "Rider GV kW": "rider_gv_kw",
    "Rider GV kWh": "rider_gv_kwh",
    "Rider OSW kW": "rider_osw_kw",
    "Rider OSW kWh": "rider_osw_kwh",
    "Rider PIPP": "rider_pipp",
    "Rider PPA": "rider_ppa",
    "Rider R kW": "rider_r_kw",
    "Rider R kWh": "rider_r_kwh",
    "Rider RBB kW": "rider_rbb_kw",
    "Rider RBB kWh": "rider_rbb_kwh",
    "Rider RGGI": "rider_rggi",
    "Rider RPS": "rider_rps",
    "Rider S kW": "rider_s_kw",
    "Rider S kWh": "rider_s_kwh",
    "Rider SMR kW": "rider_smr_kw",
    "Rider SMR kWh": "rider_smr_kwh",
    "Rider SNA kW": "rider_sna_kw",
    "Rider SNA kWh": "rider_sna_kwh",
    "Rider U1 kW": "rider_u1_kw",
    "Rider U1 kWh": "rider_u1_kwh",
    "Rider U2 kW": "rider_u2_kw",
    "Rider U2 kWh": "rider_u2_kwh",
    "Rider US-2 kW": "rider_us2_kw",
    "Rider US-2 kWh": "rider_us2_kwh",
    "Rider US-3 kW": "rider_us3_kw",
    "Rider US-3 kWh": "rider_us3_kwh",
    "Rider US-4 kW": "rider_us4_kw",
    "Rider US-4 kWh": "rider_us4_kwh",
    "Rider W kW": "rider_w_kw",
    "Rider W kWh": "rider_w_kwh",
    "Ridr GT": "rider_gt"
}

TARIFF_MAPPING = {
    "Category": "category",
    "Sub-Category": "sub_category",
    "Item": "item",
    "Condition / Tier": "condition_tier",
    "Rate / Description": "rate_description",
    "Rate": "rate",
    "Description": "description"
}

RIDER_MAPPING = {
    "RATE SCHEDULE": "rate_schedule",
    "T-CM": "t_cm",
    "B-CM": "b_cm",
    "BW-CM": "bw_cm",
    "GV-CM": "gv_cm",
    "US2-CM": "us2_cm",
    "US3-CM": "us3_cm",
    "US4-CM": "us4_cm",
    "RPS-CM": "rps_cm",
    "CE-CM": "ce_cm",
    "RBB-CM": "rbb_cm",
    "E-CM": "e_cm"
}

# ==========================================
# UPLOAD FUNCTIONS
# ==========================================

def upload_usage_data(file_path, profile_path=None):
    """Read a *pivoted* Excel sheet and push it to the DB.

    ``file_path`` may be a single Excel workbook or a directory containing
    many pivoted files.  When a companion ``profile_path`` is supplied (or
    inferred), the stem of the two filenames is compared to make sure the
    metadata comes from the correct pair.

    The key used to match files is the common prefix before the suffix
    (typically "_<date>" such as "Profile0512").
    """
    file_obj = Path(file_path)

    # running against directory: iterate over pivoted files
    if file_obj.is_dir():
        for pivoted in sorted(file_obj.glob("*_pivoted*.xls*")):
            # infer profile using same logic as below, but restricted to this stem
            stem = pivoted.stem
            suffix = pivoted.suffix
            candidate = pivoted.with_name(stem.replace("_pivoted", "_page2_parsed") + suffix)
            prof_arg = str(candidate) if candidate.exists() else None
            if prof_arg is None:
                print(f"[WARN] no profile file found for {pivoted.name}; uploading without metadata")
            else:
                print(f"paired {pivoted.name} ⇄ {candidate.name}")
            upload_usage_data(str(pivoted), profile_path=prof_arg)
        return

    print(f"Reading Usage Data from {file_path}...")
    # Read Excel, force everything to String (dtype=str) to avoid date/float errors
    try:
        df = pd.read_excel(file_path, sheet_name="pivoted", dtype=str)
    except ValueError:
        df = pd.read_excel(file_path, dtype=str)

    unmapped = sorted(set(df.columns) - set(USAGE_MAPPING.keys()))
    if unmapped:
        print("Unmapped columns (not uploaded):")
        for col in unmapped:
            print(f"  - {col}")
    
    # Rename columns using the dictionary above
    df = df.rename(columns=USAGE_MAPPING)
    
    # Keep only the columns that match our Database Table (ignore extra junk in Excel)
    valid_columns = [col for col in df.columns if col in USAGE_MAPPING.values()]
    df = df[valid_columns]

    # ------------------------------------------------------------------
    # Attempt to merge profile information (account number / customer name)
    # ------------------------------------------------------------------
    if profile_path is None:
        # infer based on naming convention
        path_obj = Path(file_path)
        stem = path_obj.stem
        if stem.endswith("_pivoted"):
            candidate = path_obj.with_name(stem.replace("_pivoted", "_page2_parsed") + path_obj.suffix)
            if candidate.exists():
                profile_path = str(candidate)
    if profile_path:
        # verify matching stems
        pf = Path(profile_path)
        if pf.stem.replace("_page2_parsed", "") != Path(file_path).stem.replace("_pivoted", ""):
            print(f"[WARNING] pivoted file '{Path(file_path).name}' and profile '{pf.name}' have mismatched keys")
        try:
            print(f"Reading profile data from {profile_path}...")
            prof_df = pd.read_excel(profile_path, dtype=str)
            # expect two columns: Label, Value
            kv = dict(zip(prof_df.iloc[:,0].astype(str), prof_df.iloc[:,1].astype(str)))
            acct = kv.get("ACCOUNT NO.", kv.get("Account Number", ""))
            cust = kv.get("Account Profile", kv.get("Customer Name", ""))
            if acct or cust:
                df["accountNumber"] = acct
                df["CompanyName"] = cust
                print("Added account/customer columns from profile file.")
        except Exception as e:
            print(f"Warning: failed to read profile file: {e}")

    # ==========================================================
    # FIX 1: Timestamp assignment moved OUTSIDE the try/catch block
    # so every single upload gets tagged properly.
    # ==========================================================
    df['uploaded_at'] = datetime.datetime.now()

    # ==========================================================
    # FIX 2: Database Constraint Safety Net
    # If the profile failed to load, we must assign a placeholder account,
    # otherwise the Postgres unique constraint will crash the upsert.
    # ==========================================================
    if "accountNumber" not in df.columns or df["accountNumber"].isnull().all():
        print("[WARNING] No Account Number found. Defaulting to 'UNKNOWN_ACCOUNT'.")
        df["accountNumber"] = "UNKNOWN_ACCOUNT"
        df["CompanyName"] = "Unknown Customer"

    print(f"Uploading {len(df)} rows to 'usage_bill'...")
    
    # Define the unique columns that determine a "duplicate" bill
    conflict_columns = ["accountNumber", "bill_from_raw", "bill_to_raw"]
    
    upsert_dataframe(
        df=df, 
        table_name='usage_bill', 
        engine=engine, 
        unique_cols=conflict_columns
    )

def upload_tariff_data(file_path, schedule_code):
    print(f"Reading Tariff Data for Schedule {schedule_code}...")
    df = pd.read_excel(file_path, dtype=str)
    
    # Add the schedule code column (e.g., '100') since it's not in the file content usually
    df['schedule_code'] = schedule_code
    
    df = df.rename(columns=TARIFF_MAPPING)
    
    # Filter valid columns
    valid_columns = [col for col in df.columns if col in TARIFF_MAPPING.values() or col == 'schedule_code']
    df = df[valid_columns]
    
    print(f"Uploading {len(df)} rows to 'tariff_rates'...")
    df.to_sql('tariff_rates', con=engine, if_exists='append', index=False)
    print("Done!")

def upload_riders(file_path):
    print(f"Reading Rider Matrix from {file_path}...")
    df = pd.read_excel(file_path, dtype=str)
    
    df = df.rename(columns=RIDER_MAPPING)
    
    # Filter valid columns
    valid_columns = [col for col in df.columns if col in RIDER_MAPPING.values()]
    df = df[valid_columns]
    
    print(f"Uploading {len(df)} rows to 'rider_rates'...")
    # For Riders, we usually want to wipe the old one ('replace')
    df.to_sql('rider_rates', con=engine, if_exists='replace', index=False)
    print("Done!")

def main():
    parser = argparse.ArgumentParser(description="Upload pivoted usage Excel data to database")
    parser.add_argument("--pivoted", help="Path to pivoted Excel file or directory containing multiple pivoted files")
    parser.add_argument("--profile", help="Optional path to companion profile Excel file (ignored when directory is provided)")
    args = parser.parse_args()

    if not args.pivoted:
        print("ERROR: --pivoted argument is required", file=sys.stderr)
        sys.exit(1)

    input_file = Path(args.pivoted)
    if not input_file.exists():
        print(f"ERROR: Input not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    profile_file = None
    if args.profile:
        profile_file = args.profile

    # delegate to upload_usage_data which now handles directories too
    upload_usage_data(str(input_file), profile_path=profile_file)


if __name__ == "__main__":
    main()