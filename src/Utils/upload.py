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
USAGE_MAPPING = {
    "Year": "year", "Month": "month", "* Subtotal": "subtotal_raw", "** Total Charges": "total_charges_raw",
    "Bill From": "bill_from_raw", "Bill To": "bill_to_raw", "Billing Days": "billing_days",
    "Billed Rate": "billed_rate", "Bill Summary": "bill_summary", "Demand": "demand",
    "Demand Charges": "demand_charges", "Demand ESS": "demand_ess", "Distribution Demand": "distribution_demand",
    "Distribution Demand Sec.": "distribution_demand_sec", "RKVA": "rkva", "Total Consumption": "total_consumption",
    "Historical Electricity Usage": "historical_usage", "Energy Charges": "energy_charges",
    "Energy DIS": "energy_dis", "Energy ESS": "energy_ess", "Fuel Charges": "fuel_charges",
    "Fuel Chg": "fuel_chg_abbr", "Basic Cust. Charges": "basic_cust_charges",
    "Basic Customer Chg": "basic_cust_chg_abbr", "Off Peak Energy ESS": "off_peak_energy_ess",
    "Off Peak Usage": "off_peak_usage", "On Peak Energy ESS": "on_peak_energy_ess",
    "On Peak Usage": "on_peak_usage", "Virginia Tax Surcharge": "tax_surcharge",
    "Transmission Demand": "transmission_demand", "Transmission Energy": "transmission_energy",
    "Other Charges/Credits": "other_charges_credits", "kW Adj ESS Secondary": "kw_adj_ess_secondary",
    "W": "w_misc", "": "unknown_symbol", "PITTSYLVANIA CNTY SRVC AUTH |": "service_auth_name",
    "Account Number": "accountNumber", "ACCOUNT NO." : "accountNumber",
    "Customer Name": "CompanyName", "Account Profile": "CompanyName",
    "Rider B kW": "rider_b_kw", "Rider B kWh": "rider_b_kwh", "Rider BW kW": "rider_bw_kw",
    "Rider BW kWh": "rider_bw_kwh", "Rider CCR": "rider_ccr", "Rider CE kW": "rider_ce_kw",
    "Rider CE kWh": "rider_ce_kwh", "Rider DIST kW": "rider_dist_kw", "Rider DIST kWh": "rider_dist_kwh",
    "Rider E kW": "rider_e_kw", "Rider E kWh": "rider_e_kwh", "Rider GEN kW": "rider_gen_kw",
    "Rider GEN kWh": "rider_gen_kwh", "Rider GT kW": "rider_gt_kw", "Rider GV kW": "rider_gv_kw",
    "Rider GV kWh": "rider_gv_kwh", "Rider OSW kW": "rider_osw_kw", "Rider OSW kWh": "rider_osw_kwh",
    "Rider PIPP": "rider_pipp", "Rider PPA": "rider_ppa", "Rider R kW": "rider_r_kw",
    "Rider R kWh": "rider_r_kwh", "Rider RBB kW": "rider_rbb_kw", "Rider RBB kWh": "rider_rbb_kwh",
    "Rider RGGI": "rider_rggi", "Rider RPS": "rider_rps", "Rider S kW": "rider_s_kw",
    "Rider S kWh": "rider_s_kwh", "Rider SMR kW": "rider_smr_kw", "Rider SMR kWh": "rider_smr_kwh",
    "Rider SNA kW": "rider_sna_kw", "Rider SNA kWh": "rider_sna_kwh", "Rider U1 kW": "rider_u1_kw",
    "Rider U1 kWh": "rider_u1_kwh", "Rider U2 kW": "rider_u2_kw", "Rider U2 kWh": "rider_u2_kwh",
    "Rider US-2 kW": "rider_us2_kw", "Rider US-2 kWh": "rider_us2_kwh", "Rider US-3 kW": "rider_us3_kw",
    "Rider US-3 kWh": "rider_us3_kwh", "Rider US-4 kW": "rider_us4_kw", "Rider US-4 kWh": "rider_us4_kwh",
    "Rider W kW": "rider_w_kw", "Rider W kWh": "rider_w_kwh", "Ridr GT": "rider_gt"
}

TARIFF_MAPPING = {
    "Category": "category", "Sub-Category": "sub_category", "Item": "item",
    "Condition / Tier": "condition_tier", "Rate / Description": "rate_description",
    "Rate": "rate", "Description": "description"
}

RIDER_MAPPING = {
    "RATE SCHEDULE": "rate_schedule", "T-CM": "t_cm", "B-CM": "b_cm",
    "BW-CM": "bw_cm", "GV-CM": "gv_cm", "US2-CM": "us2_cm", "US3-CM": "us3_cm",
    "US4-CM": "us4_cm", "RPS-CM": "rps_cm", "CE-CM": "ce_cm", "RBB-CM": "rbb_cm", "E-CM": "e_cm"
}

# ==========================================
# 1. USER BILLS UPLOAD
# ==========================================
def upload_usage_data(file_path):
    """Read a *pivoted* Excel sheet and push it to the DB."""
    file_obj = Path(file_path)

    # running against directory: iterate over pivoted files
    if file_obj.is_dir():
        for pivoted in sorted(file_obj.glob("*_pivoted*.xls*")):
            print(f"Processing {pivoted.name}...")
            upload_usage_data(str(pivoted))
        return

    print(f"Reading Usage Data from {file_path}...")
    try:
        df = pd.read_excel(file_path, sheet_name="pivoted", dtype=str)
    except ValueError:
        df = pd.read_excel(file_path, dtype=str)

    unmapped = sorted(set(df.columns) - set(USAGE_MAPPING.keys()))
    if unmapped:
        print("Unmapped columns (not uploaded):")
        for col in unmapped:
            print(f"  - {col}")
    
    df = df.rename(columns=USAGE_MAPPING)
    valid_columns = [col for col in df.columns if col in USAGE_MAPPING.values()]
    df = df[valid_columns]

    df['uploaded_at'] = datetime.datetime.now()

    if "accountNumber" not in df.columns or df["accountNumber"].isnull().all():
        print("[WARNING] No Account Number found. Defaulting to 'UNKNOWN_ACCOUNT'.")
        df["accountNumber"] = "UNKNOWN_ACCOUNT"
        df["CompanyName"] = "Unknown Customer"

    print(f"Uploading {len(df)} rows to 'usage_bill'...")
    conflict_columns = ["accountNumber", "bill_from_raw", "bill_to_raw"]
    
    upsert_dataframe(
        df=df, 
        table_name='usage_bill', 
        engine=engine, 
        unique_cols=conflict_columns
    )
# ==========================================
# 2. TARIFFS & RIDERS UPLOAD (VERSIONED)
# ==========================================
def upload_tariffs_versioned(file_path, keep_last_n_versions=5):
    """Reads a multi-tab Tariff Excel file, creates a new version, and prunes old ones."""
    print(f"Reading Multi-Tab Tariff Data from {file_path}...")
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM tariff_rates"))
        next_version = result.scalar() + 1

    # sheet_name=None reads ALL tabs at once into a dictionary of DataFrames
    excel_tabs = pd.read_excel(file_path, sheet_name=None, dtype=str)
    
    total_rows = 0
    for sheet_name, df in excel_tabs.items():
        # Clean the tab name (e.g. "Schedule 100" -> "100")
        df['schedule_code'] = str(sheet_name).replace("Schedule", "").strip()
        df['version'] = next_version
        
        df = df.rename(columns=TARIFF_MAPPING)
        valid_cols = [col for col in df.columns if col in TARIFF_MAPPING.values() or col in ['schedule_code', 'version']]
        df = df[valid_cols]
        
        # FIX: Drop empty rows (like visual separators in Excel) where the 'item' is blank
        if 'item' in df.columns:
            df = df.dropna(subset=['item'])
        
        df.to_sql('tariff_rates', con=engine, if_exists='append', index=False)
        total_rows += len(df)
        
    print(f"✅ Successfully uploaded {total_rows} rows across {len(excel_tabs)} tabs as Tariff Version {next_version}.")

    # Limit storage by deleting old versions
    if next_version > keep_last_n_versions:
        cutoff = next_version - keep_last_n_versions
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM tariff_rates WHERE version <= {cutoff}"))
        print(f"🧹 Storage Limit enforced: Deleted Tariff versions older than v{cutoff + 1}")

def upload_riders_versioned(file_path, keep_last_n_versions=5):
    """Reads a Rider Excel file, creates a new version, and prunes old ones."""
    print(f"Reading Rider Data from {file_path}...")
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM rider_rates"))
        next_version = result.scalar() + 1

    df = pd.read_excel(file_path, dtype=str)
    df['version'] = next_version
    
    df = df.rename(columns=RIDER_MAPPING)
    valid_cols = [col for col in df.columns if col in RIDER_MAPPING.values() or col == 'version']
    df = df[valid_cols]
    
    df.to_sql('rider_rates', con=engine, if_exists='append', index=False)
    print(f"✅ Successfully uploaded {len(df)} rows as Rider Version {next_version}.")

    if next_version > keep_last_n_versions:
        cutoff = next_version - keep_last_n_versions
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM rider_rates WHERE version <= {cutoff}"))
        print(f"🧹 Storage Limit enforced: Deleted Rider versions older than v{cutoff + 1}")

# ==========================================
# 3. CLI EXECUTION
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Upload pivoted usage Excel data to database")
    parser.add_argument("--pivoted", help="Path to pivoted Excel file or directory containing multiple pivoted files")
    args = parser.parse_args()

    if not args.pivoted:
        print("ERROR: --pivoted argument is required", file=sys.stderr)
        sys.exit(1)

    input_file = Path(args.pivoted)
    if not input_file.exists():
        print(f"ERROR: Input not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    # By default, running from the command line assumes you are uploading a user bill
    upload_usage_data(str(input_file))

if __name__ == "__main__":
    main()