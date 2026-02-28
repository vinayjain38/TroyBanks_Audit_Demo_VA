"""
test_data_generator.py - Generates realistic test data for va_step2_anomalies_db.py
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from src.Utils import database
    get_engine = getattr(database, "get_engine", None)
except Exception:
    get_engine = None

import sqlalchemy

def get_db_engine():
    """Get database engine"""
    if get_engine is not None:
        try:
            return get_engine()
        except Exception:
            pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return sqlalchemy.create_engine(url)


def get_db_schema():
    """Get the actual schema of the usage_bill table"""
    try:
        engine = get_db_engine()
        insp = sqlalchemy.inspect(engine)
        cols = [c["name"] for c in insp.get_columns("usage_bill")]
        return cols
    except Exception as e:
        print(f"[WARNING] Could not inspect table schema: {str(e)}")
        # Return default expected columns
        return ["bill_from_raw", "bill_to_raw", "total_consumption", "demand", 
                "total_charges_raw", "billed_rate"]


def generate_test_data():
    """Generate realistic test billing data with known anomalies"""
    
    print("=" * 60)
    print("GENERATING TEST DATA")
    print("=" * 60)
    
    # Check actual schema first
    actual_cols = get_db_schema()
    print(f"[INFO] Table columns: {actual_cols}")
    
    records = []
    
    # Account 1: Steady usage, but spike in Dec 2025
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            if year == 2025 and month > 12:  # Don't go beyond current month
                continue
            
            # Base consumption: 5000 kWh/month
            base_consumption = 5000
            
            # Add spike in Dec 2025 (60% increase)
            if year == 2025 and month == 12:
                consumption = base_consumption * 1.60
                demand = 60  # kW
            else:
                consumption = base_consumption + np.random.normal(0, 100)  # Small variance
                demand = 50  # kW
            
            consumption = max(consumption, 100)  # Ensure positive
            
            bill_from = datetime(year, month, 1)
            if month == 12:
                bill_to = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                bill_to = datetime(year, month + 1, 1) - timedelta(days=1)
            
            billing_days = (bill_to - bill_from).days + 1
            charges = consumption * 0.12  # $0.12 per kWh
            
            record = {
                "bill_from_raw": int(bill_from.strftime("%Y%m%d")),
                "bill_to_raw": int(bill_to.strftime("%Y%m%d")),
                "total_consumption": round(consumption, 2),
                "demand": round(demand, 2),
                "total_charges_raw": round(charges, 2),
                "billed_rate": 0.12,
            }
            # Add optional columns if they exist
            if "accountNumber" in actual_cols:
                record["accountNumber"] = "ACCT001"
            if "CompanyName" in actual_cols:
                record["CompanyName"] = "Riverside Manufacturing"
            records.append(record)
    
    # Account 2: Seasonal pattern with new activation marker in Jan 2025
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            if year == 2025 and month > 12:
                continue
            
            # Seasonal: higher in summer, lower in winter
            seasonal_factor = 1.5 if month in [6, 7, 8, 9] else 1.0
            base_consumption = 3000 * seasonal_factor
            
            # New activation in Jan 2025 (high spike)
            if year == 2025 and month == 1:
                consumption = 4000  # First month
                demand = 40
            else:
                consumption = base_consumption + np.random.normal(0, 50)
                demand = 30 + (5 if month in [6, 7, 8, 9] else 0)
            
            consumption = max(consumption, 100)
            
            bill_from = datetime(year, month, 1)
            if month == 12:
                bill_to = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                bill_to = datetime(year, month + 1, 1) - timedelta(days=1)
            
            billing_days = (bill_to - bill_from).days + 1
            charges = consumption * 0.10  # $0.10 per kWh
            
            record = {
                "bill_from_raw": int(bill_from.strftime("%Y%m%d")),
                "bill_to_raw": int(bill_to.strftime("%Y%m%d")),
                "total_consumption": round(consumption, 2),
                "demand": round(demand, 2),
                "total_charges_raw": round(charges, 2),
                "billed_rate": 0.10,
            }
            if "accountNumber" in actual_cols:
                record["accountNumber"] = "ACCT002"
            if "CompanyName" in actual_cols:
                record["CompanyName"] = "Metro Services Inc"
            records.append(record)
    
    # Account 3: Steady no anomalies
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            if year == 2025 and month > 12:
                continue
            
            consumption = 2000 + np.random.normal(0, 50)
            demand = 25
            consumption = max(consumption, 100)
            
            bill_from = datetime(year, month, 1)
            if month == 12:
                bill_to = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                bill_to = datetime(year, month + 1, 1) - timedelta(days=1)
            
            billing_days = (bill_to - bill_from).days + 1
            charges = consumption * 0.15
            
            record = {
                "bill_from_raw": int(bill_from.strftime("%Y%m%d")),
                "bill_to_raw": int(bill_to.strftime("%Y%m%d")),
                "total_consumption": round(consumption, 2),
                "demand": round(demand, 2),
                "total_charges_raw": round(charges, 2),
                "billed_rate": 0.15,
            }
            if "accountNumber" in actual_cols:
                record["accountNumber"] = "ACCT003"
            if "CompanyName" in actual_cols:
                record["CompanyName"] = "Tech Solutions Ltd"
            records.append(record)
    
    df = pd.DataFrame(records)
    print(f"\n[INFO] Generated {len(df)} test billing records for 3 accounts")
    print(f"       - ACCT001: Riverside Manufacturing (spike in Dec 2025)")
    print(f"       - ACCT002: Metro Services Inc (new activation Jan 2025)")
    print(f"       - ACCT003: Tech Solutions Ltd (no anomalies)")
    
    return df


def insert_test_data(df):
    """Insert test data into the database"""
    
    print("\n" + "=" * 60)
    print("INSERTING TEST DATA INTO DATABASE")
    print("=" * 60)
    
    try:
        engine = get_db_engine()
        
        # Try to delete existing test data
        with engine.connect() as conn:
            try:
                # Build WHERE clause based on actual schema
                actual_cols = get_db_schema()
                if "accountNumber" in actual_cols:
                    conn.execute(sqlalchemy.text("DELETE FROM usage_bill WHERE \"accountNumber\" IN ('ACCT001', 'ACCT002', 'ACCT003')"))
                    conn.commit()
                    print("[INFO] Cleared existing test data")
            except Exception as e:
                print(f"[NOTICE] Could not clear existing data (may not exist): {str(e)}")
        
        # Insert new test data
        df.to_sql("usage_bill", con=engine, if_exists="append", index=False)
        print(f"[SUCCESS] Inserted {len(df)} test records into usage_bill table")
        
        # Verify insertion
        verify_query = "SELECT COUNT(*) as count FROM usage_bill"
        result = pd.read_sql(verify_query, con=engine)
        count = result['count'].iloc[0]
        print(f"[VERIFY] Total records in database: {count}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to insert test data: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main: Generate and insert test data"""
    
    # Generate test data
    df = generate_test_data()
    
    # Insert into database
    success = insert_test_data(df)
    
    if success:
        print("\n" + "=" * 60)
        print("TEST DATA READY - Run va_step2_anomalies_db.py to process")
        print("=" * 60)
        print("\nExpected anomalies:")
        print("  - ACCT001 / December 2025: 60% usage spike")
        print("  - ACCT002 / January 2025: New activation (high initial usage)")
        print("\nNo anomalies expected for ACCT003")
        return 0
    else:
        print("\n[ERROR] Failed to prepare test data")
        return 1


if __name__ == "__main__":
    sys.exit(main())
