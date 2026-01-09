# riders_table.py
"""
Extracts VEPGA Rider tables from the official tariff PDF using Camelot,
cleans header rows, and exports RAW + CLEAN tables.

Input (PDF):
    data/VEPGA-Amendment-12-Effective-July-1-2025.pdf

Output folder:
    data/rider_tables/

Outputs:
    table_p{page}_t{idx}_raw.xlsx
    table_p{page}_t{idx}_clean.xlsx

Run:
    python riders_table.py
"""

import os
import re
import warnings
from pathlib import Path
from typing import List, Optional, Tuple

import camelot
import pandas as pd

# ----------------------------------------------------------
# Fixed IO (no CLI args)
# ----------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CONFIG = {
    "INPUT_PDF": DATA_DIR / "VEPGA-Amendment-12-Effective-July-1-2025.pdf",
    "OUTPUT_DIR": DATA_DIR / "rider_tables",
}

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

def _cell_contains(df: pd.DataFrame, pattern: str) -> bool:
    pat = re.compile(pattern, re.I)
    for col in df.columns:
        series = df[col].astype(str)
        if series.str.contains(pat).any():
            return True
    return False


def _likely_rate_schedule_table(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    if not _cell_contains(df, r"\bRATE\s+SCHEDULE\b"):
        return False
    if not _cell_contains(df, r"\bRIDER\b"):
        return False
    return True


def _find_header_rows(df: pd.DataFrame) -> Tuple[Optional[int], Optional[int]]:
    rider_row_idx = None
    for i in range(min(10, len(df))):
        row = df.iloc[i].astype(str).str.strip()
        non_empty = (row != "").sum()
        if non_empty == 0:
            continue
        rider_hits = row.str.fullmatch(r"RIDER", case=False).sum()
        if rider_hits / non_empty >= 0.3:
            rider_row_idx = i
            break

    if rider_row_idx is None:
        return (None, None)

    rowB = rider_row_idx + 1 if rider_row_idx + 1 < len(df) else None
    return (rider_row_idx, rowB)


def _to_string_only(val):
    if val is None:
        return None
    return str(val).strip()


def _merge_two_header_rows(df: pd.DataFrame) -> pd.DataFrame:
    iA, iB = _find_header_rows(df)

    if iA is None or iB is None:
        df2 = df.copy()
        df2.columns = [str(c).strip() for c in df2.columns]
        if "COL" in df2.columns:
            warnings.warn("Dropping unexpected 'COL' column")
            df2 = df2.drop(columns=["COL"])
        return df2

    rowA = df.iloc[iA].astype(str).str.strip().tolist()
    rowB = df.iloc[iB].astype(str).str.strip().tolist()

    headers = []
    idxs = []

    for col_idx in range(len(df.columns)):
        a = rowA[col_idx] if col_idx < len(rowA) else ""
        b = rowB[col_idx] if col_idx < len(rowB) else ""
        combined = (a + " " + b).strip()
        if combined:
            headers.append(combined)
            idxs.append(col_idx)

    body = df.iloc[iB + 1:].iloc[:, idxs].copy()
    body.columns = headers

    if "COL" in body.columns:
        warnings.warn("Dropping unexpected 'COL' column")
        body = body.drop(columns=["COL"])

    return body.reset_index(drop=True)


def clean_table(df: pd.DataFrame) -> pd.DataFrame:
    df1 = _merge_two_header_rows(df)

    df2 = df1.copy()
    for col in df2.columns:
        df2[col] = df2[col].apply(_to_string_only)

    if "COL" in df2.columns:
        warnings.warn("Dropping unexpected 'COL' column")
        df2 = df2.drop(columns=["COL"])

    # drop fully empty columns
    df2 = df2.loc[:, ~df2.apply(lambda c: c.astype(str).str.strip().eq("").all())]

    return df2


# ----------------------------------------------------------
# Core extraction
# ----------------------------------------------------------

def extract_rate_schedule_tables(pdf_path: Path) -> List[Tuple[int, pd.DataFrame]]:
    matches: List[Tuple[int, pd.DataFrame]] = []
    seen_pages = set()

    # stream pass
    try:
        stream_tables = camelot.read_pdf(
            str(pdf_path), pages="all", flavor="stream", strip_text="\n"
        )
    except Exception:
        stream_tables = []

    for t in stream_tables:
        if _likely_rate_schedule_table(t.df):
            matches.append((t.page, t.df))
            seen_pages.add(t.page)

    # lattice pass (only for pages not already matched)
    try:
        lattice_tables = camelot.read_pdf(
            str(pdf_path), pages="all", flavor="lattice", strip_text="\n"
        )
    except Exception:
        lattice_tables = []

    for t in lattice_tables:
        if t.page in seen_pages:
            continue
        if _likely_rate_schedule_table(t.df):
            matches.append((t.page, t.df))
            seen_pages.add(t.page)

    return sorted(matches, key=lambda x: x[0])


def save_table_pair(df_raw: pd.DataFrame, df_clean: pd.DataFrame,
                    out_dir: Path, page_num: int, idx: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / f"table_p{page_num}_t{idx}_raw.xlsx"
    clean_path = out_dir / f"table_p{page_num}_t{idx}_clean.xlsx"

    df_raw.to_excel(raw_path, index=False)
    df_clean.to_excel(clean_path, index=False)

    print(f"Saved RAW  : {raw_path}")
    print(f"Saved CLEAN: {clean_path}")


# ----------------------------------------------------------
# Main (no args)
# ----------------------------------------------------------

def main() -> None:
    pdf_path = Path(CONFIG["INPUT_PDF"])
    out_dir = Path(CONFIG["OUTPUT_DIR"])

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Input PDF not found at: {pdf_path}\n"
            f"Place the PDF in your data/ folder with this exact name:\n"
            f"  {pdf_path.name}"
        )

    print(f"Extracting rider tables from: {pdf_path}")
    tables = extract_rate_schedule_tables(pdf_path)

    if not tables:
        print("No Rider tables detected. PDF may be scanned image or not text-based.")
        return

    for i, (page, df_raw) in enumerate(tables, start=1):
        df_clean = clean_table(df_raw)
        save_table_pair(df_raw, df_clean, out_dir, page, i)

    print(f"Done. Extracted {len(tables)} tables into: {out_dir}")


if __name__ == "__main__":
    main()
