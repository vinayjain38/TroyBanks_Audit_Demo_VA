"""Helper to drop usage_bill table and upload one pivoted file (with profile)."""
from src.Utils.database import engine, Base
from sqlalchemy import text
from src.Utils import upload
import sys

# drop and recreate
with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS usage_bill"))
    conn.commit()
    print("dropped usage_bill")
Base.metadata.create_all(bind=engine)
print("recreated tables (including fresh usage_bill)")

# args: pivoted path and optional profile
if len(sys.argv) < 2:
    print("usage: python run_single_upload.py pivoted.xlsx [profile.xlsx]")
    sys.exit(1)

pivoted = sys.argv[1]
profile = sys.argv[2] if len(sys.argv) > 2 else None
print(f"uploading {pivoted} with profile {profile}")
upload.upload_usage_data(pivoted, profile_path=profile)

# verify
with engine.connect() as conn:
    res = conn.execute(text("SELECT count(*) FROM usage_bill"))
    count = res.scalar()
    print(f"rows in usage_bill: {count}")
    # show first few columns
    res2 = conn.execute(text("SELECT accountNumber, CompanyName, year, month FROM usage_bill LIMIT 5"))
    for row in res2:
        print(row)
