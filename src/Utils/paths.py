import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = PROJECT_ROOT / "data"
SRC_DIR = PROJECT_ROOT / "src"

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
EXPORT_DIR = DATA_DIR / "export"

SCHEDULES_XLSX = RAW_DIR / "Mini_Edit_VEPGA_Schedules_Compact.xlsx"

NEW_BILLS_DIR = RAW_DIR / "new-bills"
NEW_BILLS_PARSED_DIR = INTERIM_DIR / "new-bills-parsed"

RIDERS_PDF = RAW_DIR / "VEPGA-Amendment-12-Effective-July-1-2025.pdf"
RIDERS_DIR = INTERIM_DIR / "rider_tables_new"
RIDERS_OUT = INTERIM_DIR / "riders_new.xlsx"

OLD_USAGE_BILL_XLSB = RAW_DIR / "City_of_VA_Beach_Usage_History.xlsb"

USAGE_INT = INTERIM_DIR / "va_step1_base.xlsx"
ANOMALY_OUT = INTERIM_DIR / "va_step2_outputs.xlsx"
