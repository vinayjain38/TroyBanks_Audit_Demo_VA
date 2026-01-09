# riders_table.py

"""
# Overview
# - File: riders_table_new.py — extracts rider tables from a tariff PDF, parses per-schedule rider amounts (kWh and kW), aggregates them, and writes a human-readable Excel `riders.xlsx` that matches the schema expected by `src.app_new.py`.

# Pipeline (high level)  
# - Input: PDF at `RIDERS_PDF` (from `src.paths`).  
# - Detect rider tables in the PDF (stream + lattice modes via Camelot).  
# - For each detected raw table:
#   - Save a raw XLSX (debug/audit).  
#   - Parse each schedule row to sum per-schedule rider amounts separated by unit (/kWh or /kW).  
# - Aggregate duplicates across pages/tables.  
# - Format totals as dollar strings and write `RIDERS_OUT` XLSX.

# Key functions & responsibilities
# - `is_valid_rider_rate_table(df)`  
#   - Heuristics to accept/reject a Camelot table as a rider table: at least 6 columns, a header row containing "RATE SCHEDULE", a header block containing "RIDER", schedule-like rows below, and at least one `$` value present.

# - `extract_rate_schedule_tables(pdf_path)`  
#   - Runs Camelot (`stream` + `lattice`) and returns all tables that pass `is_valid_rider_rate_table`.

# - `_find_header_row_index(df)`  
#   - Finds the header row index by searching for "RATE SCHEDULE" (first ~30 rows).

# - `_parse_amount_unit(cell)` and `_parse_unit_only(cell)`  
#   - Parse amount strings and optional inline units. Handles patterns like `$0.001242`, `$0.001242/kWh`, `"0"`, or `"/kWh"` in an adjacent cell.

# - `_table_to_riders_totals(df_raw)`  
#   - Main parser for one raw table: locates header, iterates data rows, extracts schedule number via regex, scans columns and accumulates `kwh_sum` and `kw_sum` using inline-unit or adjacent-unit rules. Returns a DataFrame with per-schedule numeric totals.

# - `build_riders_xlsx_from_pdf_tables(tables)`  
#   - Concatenates per-table parts, groups by schedule, sums duplicates, and renames columns to the `riders.xlsx` schema (`RATE SCHEDULE`, `AGGREGATE RIDER ADJUSTMENT PER KWH`, `AGGREGATE RIDER ADJUSTMENT PER KW`).

# - `main()`  
#   - Coordinates the workflow: detect tables, save raw tables, parse and aggregate, format as `$` strings (6 decimals), write `RIDERS_XLSX`, and print confirmation.

# Important regexes / tokens
# - `RATE_SCHEDULE_RE` — matches "RATE SCHEDULE" header.  
# - `RIDER_TOKEN` — matches "RIDER" header tokens.  
# - `SCHEDULE_ROW_RE` — finds schedule numbers in first column.  
# - `INLINE_RE` — parses inline money with optional `/(kwh|kw)` unit.  
# - `UNIT_ONLY_RE` — detects adjacent unit-only cells like `/kWh`.

# Output format
# - Writes `RIDERS_OUT` Excel with columns:
#   - `RATE SCHEDULE` (e.g., "SCHEDULE 120")
#   - `AGGREGATE RIDER ADJUSTMENT PER KWH` (string like `$0.001242`)
#   - `AGGREGATE RIDER ADJUSTMENT PER KW`  (string like `$4.485000`)

# Caveats & notes
# - Camelot requires text-based (not scanned image) PDFs, and may need `ghostscript`/`tk` installed; detection may fail on scanned or badly-structured PDFs.  
# - Current output formats amounts as strings (dollar-formatted). If you need numeric columns for calculations, add numeric helper columns (commented code shows how).  
# - Heuristics assume the PDF table layout is consistent (units inline or in next column). Irregular layouts may need additional parsing rules.  
# - Duplicate schedule entries across pages are summed; ensure that’s the desired behavior.  
# - The parser ignores cells it cannot parse as amounts; review raw saved tables (`table_p{page}_t{idx}_raw.xlsx`) when debugging.

# Suggestions / small improvements
# - Export both formatted strings and numeric `_NUM` columns (uncomment helpers) so downstream code can use numbers directly.  
# - Add logging and unit tests for `_parse_amount_unit` and `_table_to_riders_totals`.  
# - Add a fallback or OCR path (e.g., `pdfplumber` → Tesseract) for scanned PDFs.  
# - Make the money-format decimal precision configurable.
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
import camelot
import pandas as pd

from src.paths import RIDERS_PDF, RIDERS_DIR, RIDERS_OUT

# BASE_DIR = Path(__file__).resolve().parent
CONFIG = {
    "INPUT_PDF": RIDERS_PDF,
    "OUTPUT_DIR": RIDERS_DIR,
    "RIDERS_XLSX": RIDERS_OUT,
}

RATE_SCHEDULE_RE  = re.compile(r"^\s*RATE\s+SCHEDULE\s*$", re.IGNORECASE)
RIDER_TOKEN       = re.compile(r"\bRIDER\b", re.IGNORECASE)
SCHEDULE_ROW_RE   = re.compile(r"(?i)\b(?:sched\w*|schd\w*|sc\w*|schedule)?\s*(\d{2,4})\b")
RATE_VALUE_RE     = re.compile(r"\$\s*\d")  # at least one money value somewhere

# ----------------------------------------------------------
# Detection helpers
# ----------------------------------------------------------

def _cell_contains(df: pd.DataFrame, pattern: str) -> bool:
    pat = re.compile(pattern, re.I)
    for col in df.columns:
        s = df[col].astype(str)
        if s.str.contains(pat).any():
            return True
    return False

## Option 1:
def _likely_rate_schedule_table(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    if not _cell_contains(df, r"\bRATE\s+SCHEDULE\b"):
        return False
    if not _cell_contains(df, r"\bRIDER\b"):
        return False
    return True

## Option 2:
def is_valid_rider_rate_table(df: pd.DataFrame) -> bool:
    """
    Accept only rider matrix tables like p95_t1_raw and p96_t2_raw:
      - has a header row where col0 == 'RATE SCHEDULE'
      - header row (or nearby rows) contains 'RIDER'
      - has schedule-like rows in col0
      - has at least one $ value somewhere
    Rejects schedule summary tables that don't have RIDER headers.
    """
    if df is None or df.empty:
        return False

    # rider tables are wide; narrative and summary tables often are not
    if df.shape[1] < 6:
        return False

    # Find header row where first col is RATE SCHEDULE
    header_row = None
    for i in range(min(30, len(df))):
        if RATE_SCHEDULE_RE.match(str(df.iat[i, 0]).strip()):
            header_row = i
            break
    if header_row is None:
        return False

    # Require 'RIDER' appears in header row OR one row above it
    header_block = df.iloc[max(header_row - 1, 0):header_row + 1].astype(str)
    has_rider = header_block.apply(
        lambda col: col.str.contains(RIDER_TOKEN, na=False)
    ).any().any()
    if not has_rider:
        return False

    # Must have schedule-like rows below header in col0
    col0 = df.iloc[header_row + 1:, 0].astype(str).str.strip()
    nonempty = col0[col0.ne("") & col0.ne("nan")]
    if len(nonempty) == 0:
        return False
    if not nonempty.apply(lambda x: bool(SCHEDULE_ROW_RE.search(x))).any():
        return False

    # Must contain at least one $ numeric value somewhere
    flat = df.astype(str).values.flatten()
    if not any(RATE_VALUE_RE.search(x) for x in flat):
        return False

    return True

# ----------------------------------------------------------
# Core extraction (RAW)
# ----------------------------------------------------------

def extract_rate_schedule_tables(pdf_path: Path) -> List[Tuple[int, pd.DataFrame]]:
    """Return list of (page, raw_df) tables that look like rider tables."""
    matches: List[Tuple[int, pd.DataFrame]] = []
    seen_pages = set()

    try:
        stream = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream", strip_text="\n")
    except Exception:
        stream = []

    for t in stream:
        ## Option 1:
        # if _likely_rate_schedule_table(t.df):
        #     matches.append((t.page, t.df))
        #     seen_pages.add(t.page)
        ## Option 2:
        if is_valid_rider_rate_table(t.df):
            matches.append((t.page, t.df))
            seen_pages.add(t.page)

    try:
        lattice = camelot.read_pdf(str(pdf_path), pages="all", flavor="lattice", strip_text="\n")
    except Exception:
        lattice = []

    for t in lattice:
        if t.page in seen_pages:
            continue
        ## Option 1:
        # if _likely_rate_schedule_table(t.df):
        #     matches.append((t.page, t.df))
        #     seen_pages.add(t.page)
        ## Option 2:
        if is_valid_rider_rate_table(t.df):
            matches.append((t.page, t.df))
            seen_pages.add(t.page)

    return sorted(matches, key=lambda x: x[0])


def save_raw_table(df_raw: pd.DataFrame, out_dir: Path, page_num: int, idx: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"table_p{page_num}_t{idx}_raw.xlsx"
    df_raw.to_excel(raw_path, index=False)
    return raw_path


# ----------------------------------------------------------
# Parsing riders from RAW table
# ----------------------------------------------------------

# Money + optional inline unit
INLINE_RE = re.compile(
    r"^\s*\$?\s*([0-9,]*\.?[0-9]+)\s*(?:/\s*(kwh|kw))?\s*$",
    re.IGNORECASE
)

# Unit-only cell like "/kWh" or "/KW"
UNIT_ONLY_RE = re.compile(r"^\s*/\s*(kwh|kw)\s*$", re.IGNORECASE)


def _parse_amount_unit(cell: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse a raw cell that may look like:
        "$0.001242"
        "$0.001242/kWh"
        "$4.485/KW"
        "0"
        ""
    Returns: (amount, unit) where unit is "kwh" or "kw" (lower) or None.
    """
    if cell is None:
        return (None, None)

    s = str(cell).strip()
    if not s or s.lower() == "nan":
        return (None, None)

    m = INLINE_RE.match(s.replace(" ", ""))
    if not m:
        return (None, None)

    amt_str = m.group(1)
    unit = m.group(2).lower() if m.group(2) else None

    try:
        amt = float(amt_str.replace(",", ""))
    except Exception:
        return (None, None)

    return (amt, unit)


def _parse_unit_only(cell: str) -> Optional[str]:
    if cell is None:
        return None
    s = str(cell).strip()
    m = UNIT_ONLY_RE.match(s)
    if not m:
        return None
    return m.group(1).lower()


def _find_header_row_index(df: pd.DataFrame) -> Optional[int]:
    """
    Find the row that contains "RATE SCHEDULE" as the first cell (or anywhere).
    We use this to locate where schedule rows begin.
    """
    for i in range(min(len(df), 30)):
        row = df.iloc[i].astype(str).str.upper()
        if row.str.contains("RATE SCHEDULE", na=False).any():
            return i
    return None


def _table_to_riders_totals(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Convert one RAW rider table into per-schedule totals:
        schedule_code, rider_total_per_kwh, rider_total_per_kw

    Works when:
      - units are inline (value cell contains /kWh or /KW), OR
      - units are adjacent in the next column (unit-only column).
    """
    df = df_raw.copy()

    header_idx = _find_header_row_index(df)
    if header_idx is None:
        return pd.DataFrame(columns=["schedule_code", "rider_total_per_kwh", "rider_total_per_kw"])

    # Data rows come after header_idx (and typically after one category row like "PUBLIC AUTHORITY")
    data = df.iloc[header_idx + 1:].reset_index(drop=True)

    results = []

    for _, row in data.iterrows():
        first = str(row.iloc[0]).strip()
        m = SCHEDULE_ROW_RE.search(first)
        if not m:
            continue

        sched_num = m.group(1)  # e.g., "100"
        sched_text = f"SCHEDULE {sched_num}"  # normalized spelling

        kwh_sum = 0.0
        kw_sum = 0.0

        # iterate across remaining columns and parse amounts/units
        # strategy:
        #   - if amount cell has inline unit -> use it
        #   - else if next cell is unit-only -> use that unit
        #   - else ignore that cell
        col_count = len(row)

        c = 1
        while c < col_count:
            cell = row.iloc[c]
            amt, unit = _parse_amount_unit(cell)

            if amt is None:
                c += 1
                continue

            if unit is None:
                # check adjacent cell for unit-only
                if c + 1 < col_count:
                    adj_unit = _parse_unit_only(row.iloc[c + 1])
                    if adj_unit in ("kwh", "kw"):
                        unit = adj_unit
                        # consume the unit cell
                        c += 2
                    else:
                        c += 1
                else:
                    c += 1
            else:
                c += 1

            # add to totals based on unit
            if unit == "kwh":
                kwh_sum += amt
            elif unit == "kw":
                kw_sum += amt
            else:
                # unknown unit -> ignore
                pass

        results.append(
            {
                "schedule_code": sched_text,   # matches your load_riders() str.contains("SCHEDULE 100")
                "rider_total_per_kwh": kwh_sum,
                "rider_total_per_kw": kw_sum,
            }
        )

    return pd.DataFrame(results)


def build_riders_xlsx_from_pdf_tables(tables: List[Tuple[int, pd.DataFrame]]) -> pd.DataFrame:
    """
    Combine all detected tables into a single riders dataframe.
    If duplicate schedules appear across tables, sums them.
    """
    all_parts = []
    for page, df_raw in tables:
        part = _table_to_riders_totals(df_raw)
        if not part.empty:
            all_parts.append(part)

    if not all_parts:
        return pd.DataFrame(columns=["RATE SCHEDULE", "AGGREGATE RIDER ADJUSTMENT PER KWH", "AGGREGATE RIDER ADJUSTMENT PER KW"])

    combined = pd.concat(all_parts, ignore_index=True)

    # group in case same schedule appears multiple times across tables/pages
    combined = (
        combined.groupby("schedule_code", as_index=False)[["rider_total_per_kwh", "rider_total_per_kw"]]
        .sum()
    )

    # match your existing riders.xlsx schema + load_riders() expectation
    out = combined.rename(
        columns={
            "schedule_code": "RATE SCHEDULE",
            "rider_total_per_kwh": "AGGREGATE RIDER ADJUSTMENT PER KWH",
            "rider_total_per_kw": "AGGREGATE RIDER ADJUSTMENT PER KW",
        }
    )

    return out


# ----------------------------------------------------------
# Main
# ----------------------------------------------------------

def main() -> None:
    pdf_path = Path(CONFIG["INPUT_PDF"])
    out_dir = Path(CONFIG["OUTPUT_DIR"])
    riders_xlsx = Path(CONFIG["RIDERS_XLSX"])

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Input PDF not found: {pdf_path}\n"
            f"Place PDF in data/ with exact name: {pdf_path.name}"
        )

    print(f"Extracting rider tables from: {pdf_path}")
    tables = extract_rate_schedule_tables(pdf_path)

    if not tables:
        print("No rider tables detected. PDF may be scanned or not text-based.")
        return

    # Save RAW tables (optional but useful for debugging/auditing)
    for idx, (page, df_raw) in enumerate(tables, start=1):
        raw_path = save_raw_table(df_raw, out_dir, page, idx)
        print(f"Saved RAW table: {raw_path.name}")

    # Build riders.xlsx totals
    riders_df = build_riders_xlsx_from_pdf_tables(tables)

    if riders_df.empty:
        print("No schedule rows detected while parsing rider tables.")
        return


    # --- Write human-readable riders.xlsx with $ formatting ---
    AGG_KWH_COL = "AGGREGATE RIDER ADJUSTMENT PER KWH"
    AGG_KW_COL  = "AGGREGATE RIDER ADJUSTMENT PER KW"

    # --- create human-readable string versions (keep numeric too, optional) ---
    # # If you don't want numeric columns at all in the output, remove the *_NUM lines.
    # riders_df[AGG_KWH_COL + "_NUM"] = pd.to_numeric(riders_df[AGG_KWH_COL], errors="coerce").fillna(0.0)
    # riders_df[AGG_KW_COL  + "_NUM"] = pd.to_numeric(riders_df[AGG_KW_COL],  errors="coerce").fillna(0.0)

    # Format as $ strings (choose decimals you want)
    riders_df[AGG_KWH_COL] = riders_df[AGG_KWH_COL].map(lambda x: f"${x:.6f}")
    riders_df[AGG_KW_COL]  = riders_df[AGG_KW_COL].map(lambda x: f"${x:.6f}")

    # (Optional) drop numeric helper columns from export
    # riders_df = riders_df.drop(columns=[AGG_KWH_COL + "_NUM", AGG_KW_COL + "_NUM"])

    # Write human-readable Excel
    riders_df.to_excel(riders_xlsx, index=False)
    print(f"✅ Wrote riders summary file: {riders_xlsx}")
    print(riders_df.head(10))


if __name__ == "__main__":
    main()
