import hashlib
import json
import pandas as pd
import argparse
import sys
import uuid
from pathlib import Path
from src.Utils.database import engine
from sqlalchemy import text #,inspect
import datetime
from src.Utils.db_upsert import upsert_dataframe


def usage_batch_id_from_bytes(content: bytes) -> str:
    """Stable batch id for identical file bytes (same PDF / same pivoted workbook re-upload replaces)."""
    digest = hashlib.sha256(content).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"troybanks.usage.v1:{digest}"))


def usage_batch_id_from_path(path: Path) -> str:
    return usage_batch_id_from_bytes(path.read_bytes())

# ==========================================
# CONFIGURATION: COLUMN MAPPINGS
# ==========================================
# This tells Python: "When you see '* Subtotal' in Excel, put it in 'subtotal_raw' in DB"

USAGE_MAPPING = {
    "AccountNumber": "accountNumber",
    "Account Number": "accountNumber",
    "ACCOUNT NO.": "accountNumber",
    "contract_account": "accountNumber",
    "CompanyName": "accountName",
    "Account Name": "accountName",
    "Customer": "accountName",
    "Customer Name": "accountName",
    "customer": "accountName",
    "Account Profile": "accountName",

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
    # "�": "unknown_symbol",
    # "PITTSYLVANIA CNTY SRVC AUTH |": "service_auth_name",
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
    "Date": "effective_date",
    "Effective Date": "effective_date",
    "Category": "category",
    "Sub-Category": "sub_category",
    "Item": "item",
    "Condition / Tier": "condition_tier",
    "Rate / Description": "rate_description",
    "Rate": "rate",
    "Description": "description"
}

RIDER_MAPPING = {
    "Date": "effective_date",
    "Effective Date": "effective_date",
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


def _table_exists(table_name: str) -> bool:
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": table_name},
            ).fetchone()
            return result is not None

        result = conn.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"public.{table_name}"},
        ).scalar()
        return bool(result)


def _column_exists(table_name: str, column_name: str) -> bool:
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).mappings().all()
            return any(row["name"] == column_name for row in rows)

        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table_name AND column_name = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        ).fetchone()
        return bool(result)


def _ensure_reference_columns():
    """Ensure optional version-date columns exist for uploads."""
    if engine.dialect.name == "sqlite":
        if _table_exists("tariff_rates") and not _column_exists("tariff_rates", "effective_date"):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tariff_rates ADD COLUMN effective_date DATE;"))
        if _table_exists("rider_rates") and not _column_exists("rider_rates", "effective_date"):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE rider_rates ADD COLUMN effective_date DATE;"))
        return

    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF to_regclass('public.tariff_rates') IS NOT NULL THEN
                    ALTER TABLE tariff_rates ADD COLUMN IF NOT EXISTS effective_date DATE;
                END IF;
            END
            $$;
        """))
        conn.execute(text("""
            DO $$
            BEGIN
                IF to_regclass('public.rider_rates') IS NOT NULL THEN
                    ALTER TABLE rider_rates ADD COLUMN IF NOT EXISTS effective_date DATE;
                END IF;
            END
            $$;
        """))


def _ensure_usage_bill_batch_columns():
    """Add batch/source columns, backfill legacy rows, and ensure upsert uniqueness on batch + bill period."""
    if engine.dialect.name == "sqlite":
        if not _table_exists("usage_bill"):
            return
        with engine.begin() as conn:
            if not _column_exists("usage_bill", "batch_id"):
                conn.execute(text("ALTER TABLE usage_bill ADD COLUMN batch_id VARCHAR(64);"))
            if not _column_exists("usage_bill", "source_pdf"):
                conn.execute(text("ALTER TABLE usage_bill ADD COLUMN source_pdf VARCHAR(512);"))
            if not _column_exists("usage_bill", "account_profile_json"):
                conn.execute(text("ALTER TABLE usage_bill ADD COLUMN account_profile_json TEXT;"))
            conn.execute(text(
                "UPDATE usage_bill "
                "SET batch_id = 'legacy-' || id "
                "WHERE batch_id IS NULL OR TRIM(COALESCE(batch_id, '')) = '';"
            ))
            conn.execute(text("DROP INDEX IF EXISTS uix_account_bill_dates;"))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_bill_batch_period_unique "
                "ON usage_bill (batch_id, bill_from_raw, bill_to_raw);"
            ))
        return

    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF to_regclass('public.usage_bill') IS NOT NULL THEN
                    ALTER TABLE usage_bill ADD COLUMN IF NOT EXISTS batch_id VARCHAR(64);
                    ALTER TABLE usage_bill ADD COLUMN IF NOT EXISTS source_pdf VARCHAR(512);
                    ALTER TABLE usage_bill ADD COLUMN IF NOT EXISTS account_profile_json TEXT;
                END IF;
            END
            $$;
        """))
        conn.execute(text("""
            UPDATE usage_bill
            SET batch_id = 'legacy-' || id::text
            WHERE batch_id IS NULL OR TRIM(COALESCE(batch_id, '')) = '';
        """))
        # Legacy uniqueness on (account, bill dates) blocks multiple upload batches per account.
        # Upserts use (batch_id, bill_from_raw, bill_to_raw); drop old constraint/index if present.
        conn.execute(text('ALTER TABLE usage_bill DROP CONSTRAINT IF EXISTS uix_account_bill_dates;'))
        conn.execute(text("DROP INDEX IF EXISTS uix_account_bill_dates;"))
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_bill_batch_period_unique
                ON usage_bill (batch_id, bill_from_raw, bill_to_raw);
            """))
    except Exception as exc:
        print(f"[WARN] Could not ensure batch-period unique index (may already exist or need deduping): {exc}")


def _coerce_effective_date(value):
    """Normalize date-like values into Python date objects."""
    if value is None or value == "":
        return pd.NaT
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed.date()



# ==========================================
# 1. USER BILLS UPLOAD
# ==========================================
def _prepare_usage_dataframe(source_df, file_stem, source_name, batch_id=None, source_pdf=None, profile=None):
    """Normalize a pivoted usage DataFrame into DB columns."""
    df = source_df.copy()

    unmapped = sorted(set(df.columns) - set(USAGE_MAPPING.keys()))
    if unmapped:
        print("Unmapped columns (not uploaded):")
        for col in unmapped:
            print(f"  - {col}")

    df = df.rename(columns=USAGE_MAPPING)
    valid_columns = [col for col in df.columns if col in USAGE_MAPPING.values()]
    df = df[valid_columns]

    df['uploaded_at'] = datetime.datetime.now()

    if "accountNumber" in df.columns:
        df["accountNumber"] = df["accountNumber"].astype(str).str.strip()
        df.loc[df["accountNumber"].isin(["", "nan", "None"]), "accountNumber"] = None
    else:
        df["accountNumber"] = None

    if "accountName" in df.columns:
        df["accountName"] = df["accountName"].astype(str).str.strip()
        df.loc[df["accountName"].isin(["", "nan", "None"]), "accountName"] = None
    else:
        df["accountName"] = None

    # Fallback for files where account columns have different headers.
    if df["accountNumber"].isnull().all():
        for col in ("contract_account", "ACCOUNT NO.", "AccountNumber", "Account Number"):
            if col in source_df.columns:
                fallback = source_df[col].astype(str).str.strip()
                fallback = fallback.where(~fallback.isin(["", "nan", "None"]), None)
                if fallback.notnull().any():
                    df["accountNumber"] = fallback
                    break

    if df["accountName"].isnull().all():
        for col in ("customer", "Account Profile", "CompanyName", "Customer", "Account Name"):
            if col in source_df.columns:
                fallback = source_df[col].astype(str).str.strip()
                fallback = fallback.where(~fallback.isin(["", "nan", "None"]), None)
                if fallback.notnull().any():
                    df["accountName"] = fallback
                    break

    if df["accountNumber"].isnull().all():
        file_fallback_account = f"UNKNOWN_{file_stem}"
        print(f"[WARNING] No Account Number found. Defaulting to '{file_fallback_account}'.")
        df["accountNumber"] = file_fallback_account
    if df["accountName"].isnull().all():
        df["accountName"] = f"Unknown Customer ({file_stem})"

    if profile:
        acct_pdf = str(profile.get("ACCOUNT NO.", "")).strip()
        if acct_pdf and acct_pdf.lower() not in ("", "nan", "none"):
            df["accountNumber"] = acct_pdf
        name_pdf = str(profile.get("Account Profile", "")).strip()
        if name_pdf and name_pdf.lower() not in ("", "nan", "none"):
            df["accountName"] = name_pdf

    df["batch_id"] = batch_id
    df["source_pdf"] = source_pdf if source_pdf is not None else source_name
    df["account_profile_json"] = json.dumps(profile, ensure_ascii=False) if profile else None
    return df


def _replace_usage_dataframe(df, table_name="usage_bill"):
    _ensure_usage_bill_batch_columns()
    batch_id = str(df["batch_id"].dropna().iloc[0]).strip() if "batch_id" in df.columns and df["batch_id"].notna().any() else ""
    if batch_id:
        with engine.begin() as conn:
            conn.execute(text(f'DELETE FROM {table_name} WHERE batch_id = :bid'), {"bid": batch_id})

    print(f"Uploading {len(df)} rows to '{table_name}'...")
    conflict_columns = ["batch_id", "bill_from_raw", "bill_to_raw"]
    upsert_dataframe(
        df=df,
        table_name=table_name,
        engine=engine,
        unique_cols=conflict_columns,
    )


def upload_usage_dataframe(source_df, batch_id, source_pdf=None, profile=None, source_name="uploaded_dataframe"):
    """Push an already-pivoted usage DataFrame to DB without writing/reading Excel."""
    df = _prepare_usage_dataframe(
        source_df=source_df,
        file_stem=Path(source_name).stem,
        source_name=source_name,
        batch_id=batch_id,
        source_pdf=source_pdf,
        profile=profile,
    )
    _replace_usage_dataframe(df)


def upload_usage_data(file_path, batch_id=None, source_pdf=None, profile=None):
    """Read a *pivoted* Excel sheet and push it to the DB.

    If ``batch_id`` is omitted, it is derived from the **file bytes** (SHA-256),
    so the same PDF / workbook always maps to the same batch. Existing rows for
    that batch are deleted first, then replaced (re-upload of the same file
    overwrites the prior snapshot). A different file for the same account gets a
    different batch id and **adds** rows alongside earlier uploads.

    ``profile`` may supply Dominion PDF fields to set account/customer consistently.
    """
    file_obj = Path(file_path)

    # running against directory: iterate over pivoted files
    if file_obj.is_dir():
        for pivoted in sorted(file_obj.glob("*_pivoted*.xls*")):
            print(f"Processing {pivoted.name}...")
            upload_usage_data(str(pivoted), batch_id=None, source_pdf=None, profile=None)
        return

    print(f"Reading Usage Data from {file_path}...")
    try:
        source_df = pd.read_excel(file_path, sheet_name="pivoted", dtype=str)
    except ValueError:
        source_df = pd.read_excel(file_path, dtype=str)

    if not batch_id:
        batch_id = usage_batch_id_from_path(file_obj)
    df = _prepare_usage_dataframe(
        source_df=source_df,
        file_stem=file_obj.stem,
        source_name=file_obj.name,
        batch_id=batch_id,
        source_pdf=source_pdf,
        profile=profile,
    )
    _replace_usage_dataframe(df)

# ==========================================
# 2. TARIFFS & RIDERS UPLOAD (VERSIONED)
# ==========================================
def upload_tariffs_versioned(file_path, keep_last_n_versions=5, effective_date=None):
    """Reads a multi-tab Tariff Excel file, creates a new version, and prunes old ones."""
    print(f"Reading Multi-Tab Tariff Data from {file_path}...")
    _ensure_reference_columns()
    
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

        # Set effective date from UI override first, else from file column if available
        if effective_date is not None:
            parsed_effective = _coerce_effective_date(effective_date)
            df["effective_date"] = parsed_effective
        elif "effective_date" in df.columns:
            df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce").dt.date
        else:
            df["effective_date"] = pd.NaT
        
        df.to_sql('tariff_rates', con=engine, if_exists='append', index=False)
        total_rows += len(df)
        
    print(f"Successfully uploaded {total_rows} rows across {len(excel_tabs)} tabs as Tariff Version {next_version}.")

    # Limit storage by deleting old versions
    if next_version > keep_last_n_versions:
        cutoff = next_version - keep_last_n_versions
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM tariff_rates WHERE version <= {cutoff}"))
        print(f"Storage Limit enforced: Deleted Tariff versions older than v{cutoff + 1}")

def upload_riders_versioned(file_path, keep_last_n_versions=5, effective_date=None):
    """Reads a Rider Excel file, creates a new version, and prunes old ones."""
    print(f"Reading Rider Data from {file_path}...")
    _ensure_reference_columns()
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM rider_rates"))
        next_version = result.scalar() + 1

    df = pd.read_excel(file_path, dtype=str)
    df['version'] = next_version
    
    df = df.rename(columns=RIDER_MAPPING)
    valid_cols = [col for col in df.columns if col in RIDER_MAPPING.values() or col == 'version']
    df = df[valid_cols]

    if effective_date is not None:
        parsed_effective = _coerce_effective_date(effective_date)
        df["effective_date"] = parsed_effective
    elif "effective_date" in df.columns:
        df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce").dt.date
    else:
        df["effective_date"] = pd.NaT
    
    df.to_sql('rider_rates', con=engine, if_exists='append', index=False)
    print(f"Successfully uploaded {len(df)} rows as Rider Version {next_version}.")

    if next_version > keep_last_n_versions:
        cutoff = next_version - keep_last_n_versions
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM rider_rates WHERE version <= {cutoff}"))
        print(f"Storage Limit enforced: Deleted Rider versions older than v{cutoff + 1}")

def main():
    parser = argparse.ArgumentParser(description="Upload pivoted usage Excel data to database")
    parser.add_argument("--pivoted", help="Path to pivoted Excel file")
    args = parser.parse_args()

    if not args.pivoted:
        print("ERROR: --pivoted argument is required", file=sys.stderr)
        sys.exit(1)

    input_file = Path(args.pivoted)
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    if input_file.suffix.lower() not in {".xlsx", ".xls"}:
        print(f"ERROR: Input must be an Excel file (.xlsx or .xls): {input_file}", file=sys.stderr)
        sys.exit(1)

    # By default, running from the command line assumes you are uploading a user bill
    upload_usage_data(str(input_file))


if __name__ == "__main__":
    main()
