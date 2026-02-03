import pandas as pd
from src.Utils.database import engine
from sqlalchemy import text

# ==========================================
# CONFIGURATION: COLUMN MAPPINGS
# ==========================================
# This tells Python: "When you see '* Subtotal' in Excel, put it in 'subtotal_raw' in DB"

USAGE_MAPPING = {
    "* Subtotal": "subtotal_raw",
    "** Total Charges": "total_charges_raw",
    "Bill From": "bill_from_raw",
    "Bill To": "bill_to_raw",
    "Billing Days": "billing_days",
    "Billed Rate": "billed_rate",
    "Bill Summary": "bill_summary",
    "Demand": "demand",
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
    "Transmission Energy": "transmission_energy",
    "Other Charges/Credits": "other_charges_credits",
    "PITTSYLVANIA CNTY SRVC AUTH |": "service_auth_name",
    # Riders
    "Rider B kWh": "rider_b_kwh",
    "Rider BW kWh": "rider_bw_kwh",
    "Rider CCR": "rider_ccr",
    "Rider CE kWh": "rider_ce_kwh",
    "Rider DIST kWh": "rider_dist_kwh",
    "Rider E kWh": "rider_e_kwh",
    "Rider GEN kWh": "rider_gen_kwh",
    "Rider GV kWh": "rider_gv_kwh",
    "Rider OSW KWh": "rider_osw_kwh",
    "Rider PIPP": "rider_pipp",
    "Rider PPA": "rider_ppa",
    "Rider R kWh": "rider_r_kwh",
    "Rider RBB kWh": "rider_rbb_kwh",
    "Rider RGGI": "rider_rggi",
    "Rider RPS": "rider_rps",
    "Rider S kWh": "rider_s_kwh",
    "Rider SMR KWh": "rider_smr_kwh",
    "Rider SNA KWh": "rider_sna_kwh",
    "Rider U1 kWh": "rider_u1_kwh",
    "Rider U2 kWh": "rider_u2_kwh",
    "Rider US-2 kWh": "rider_us2_kwh",
    "Rider US-3 kWh": "rider_us3_kwh",
    "Rider US-4 kWh": "rider_us4_kwh",
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

def upload_usage_data(file_path):
    print(f"Reading Usage Data from {file_path}...")
    # Read Excel, force everything to String (dtype=str) to avoid date/float errors
    df = pd.read_excel(file_path, dtype=str)
    
    # Rename columns using the dictionary above
    df = df.rename(columns=USAGE_MAPPING)
    
    # Keep only the columns that match our Database Table (ignore extra junk in Excel)
    valid_columns = [col for col in df.columns if col in USAGE_MAPPING.values() or col in ['year', 'month']]
    df = df[valid_columns]
    
    print(f"Uploading {len(df)} rows to 'usage_records'...")
    # if_exists='append' adds to existing data. Use 'replace' to wipe and start over.
    df.to_sql('usage_records', con=engine, if_exists='append', index=False)
    print("Done!")

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

# ==========================================
# MAIN EXECUTION (EDIT THIS PART)
# ==========================================
if __name__ == "__main__":
    
    # 1. Upload Usage Data (Change filename to your actual file)
    # upload_usage_data("Example.xlsx") 
    
    # 2. Upload Riders (Change filename)
    # upload_riders("Riders_Info.xlsx")
    
    # 3. Upload Tariffs (If you have separate files for schedules)
    # upload_tariff_data("Schedule_100.xlsx", "100")
    # upload_tariff_data("Schedule_130.xlsx", "130")
    
    print("All uploads complete.")