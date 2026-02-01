from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = ROOT / "data"

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
EXPORT_DIR = DATA_DIR / "export"
RIDERS_DIR = DATA_DIR / "rider_tables_new"
# DEBUG_DIR = DATA_DIR / "debug"

USAGE_XLSB = RAW_DIR / "City_of_VA_Beach_Usage_History.xlsb"
SCHEDULES_XLSX = RAW_DIR / "Mini_Edit_VEPGA_Schedules_Compact.xlsx"
RIDERS_PDF = RAW_DIR / "VEPGA-Amendment-12-Effective-July-1-2025.pdf"

USAGE_INT = INTERIM_DIR / "va_step1_base.xlsx"
ANOMALY_OUT = INTERIM_DIR / "va_step2_outputs.xlsx"
RIDERS_OUT = INTERIM_DIR / "riders_new.xlsx"
