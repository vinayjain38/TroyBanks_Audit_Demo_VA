# seed_database.py
import pandas as pd
from src.Utils.database import engine
from src.Utils.paths import SCHEDULES_XLSX, RIDERS_OUT

# ==========================================
# MAPPINGS
# ==========================================
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

def seed_tariffs(file_path, schedule_code="100"):
    print(f"Seeding Tariff Data for Schedule {schedule_code} from {file_path}...")
    try:
        df = pd.read_excel(file_path, dtype=str)
        df['schedule_code'] = schedule_code
        df = df.rename(columns=TARIFF_MAPPING)
        
        valid_columns = [col for col in df.columns if col in TARIFF_MAPPING.values() or col == 'schedule_code']
        df = df[valid_columns]
        
        df.to_sql('tariff_rates', con=engine, if_exists='replace', index=False)
        print(f"✅ Successfully seeded {len(df)} Tariff rows.")
    except Exception as e:
        print(f"❌ Failed to seed Tariffs: {e}")

def seed_riders(file_path):
    print(f"Seeding Rider Matrix from {file_path}...")
    try:
        df = pd.read_excel(file_path, dtype=str)
        df = df.rename(columns=RIDER_MAPPING)
        
        valid_columns = [col for col in df.columns if col in RIDER_MAPPING.values()]
        df = df[valid_columns]
        
        df.to_sql('rider_rates', con=engine, if_exists='replace', index=False)
        print(f"✅ Successfully seeded {len(df)} Rider rows.")
    except Exception as e:
        print(f"❌ Failed to seed Riders: {e}")

if __name__ == "__main__":
    print("=== STARTING DATABASE SEED ===")
    seed_tariffs(SCHEDULES_XLSX)
    seed_riders(RIDERS_OUT)
    print("=== SEEDING COMPLETE ===")