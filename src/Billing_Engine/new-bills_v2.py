# @title Sucess for page 3+, Run for all pages - get text

# !pip install pymupdf pillow pytesseract pandas openpyxl python-dotenv

import io, os, re
import sys
import fitz
import pandas as pd
from PIL import Image
from pathlib import Path
from glob import glob

import pytesseract
from pytesseract import Output

# Adjust .parents[x] based on how deep this file is stored
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.Utils.paths import NEW_BILLS_DIR, NEW_BILLS_PARSED_DIR

pdf_folder = NEW_BILLS_DIR
pdf_folder.mkdir(parents=True, exist_ok=True)

output_folder = NEW_BILLS_PARSED_DIR
output_folder.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None 

# Load environment variables from .env file when available
env_path = PROJECT_ROOT / ".env"
if env_path.exists() and load_dotenv is not None:
    load_dotenv(env_path)


# Add Tesseract to PATH from environment variables
tesseract_path = os.getenv('TESSERACT_PATH')
tessdata_prefix = os.getenv('TESSDATA_PREFIX')

if tesseract_path:
    os.environ['PATH'] = tesseract_path + os.pathsep + os.environ.get('PATH', '')
if tessdata_prefix:
    os.environ['TESSDATA_PREFIX'] = tessdata_prefix

# PDF_PATH = "../data/new-bills/Profile0412.pdf"
DPI = 400 

MONTHS_ORDER = ["JAN","FEB","MAR","APR","MAY","JUN",
                "JUL","AUG","SEP","OCT","NOV","DEC"]

# Labels to drop before writing to Excel: matched by regex pattern (case-insensitive).
# Patterns match the intent (keywords), not exact wording.
EXCLUDED_LABEL_PATTERNS = [
    r"excludes\s+taxes\s+.*facilities\s+charges|facilities\s+charges",  # * Excludes taxes and facilities charges
    r"excludes\s+one[- ]?time\s+bill\s+credits",                        # ** Excludes one-time bill credits
    r"below\s+the\s+actual|billing\s+details\s+for\s+this",             # Below the actual and billing details...
    r"usage\s+account\s+year",                                           # are usage account year
]

# Same concept, different wording by year/section due to coordinate/line-split extraction quirks.
# Applied after extraction so pivoted columns stay consistent.
LABEL_ALIASES = {
    "On ESS": "On Peak Energy ESS",
}

# Vertical grouping of words into lines (pixels). Larger = merge rows that are slightly
# offset (fixes "On ESS" vs "On Peak Energy ESS" when the PDF uses one row but coords split it).
LINE_GROUP_PX = 20

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def render_page_to_image(pdf_path: str, page_index: int, dpi: int = 300):
    doc = fitz.open(pdf_path)
    if page_index < 0 or page_index >= len(doc):
        raise IndexError(f"PDF has {len(doc)} pages, got {page_index}")
    page = doc[page_index]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    doc.close()
    return img

def is_month_token(text: str) -> bool:
    return text.upper() in MONTHS_ORDER

def is_value_token(text: str) -> bool:
    """
    Tokens that look like dates, numbers, money, or 3-digit rate codes
    like VE-100 / VE-120. Things like 'U1', 'US-2', 'kWh' remain FALSE.
    """
    t = text.replace(",", "")

    # Money
    if "$" in t:
        return True

    # Dates  (MM/DD/YY or MM/DD/YYYY)
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t):
        return True

    # Plain numbers (integers or decimals)
    if re.match(r"^[+-]?\d+(\.\d+)?$", t):
        return True

    # Rate codes like VE-100, VE-120 (2–3 letters, hyphen, 3 digits)
    if re.match(r"^[A-Za-z]{2,3}-\d{3}$", t):
        return True

    # Otherwise: treat as label text (e.g., U1, US-2, kWh)
    return False

# -------------------------------------------------
# Extract a single table from a page (coords-based)
# -------------------------------------------------
def extract_usage_table_by_coords(pdf_path: str,
                                  page_index: int,
                                  dpi: int = 300,
                                  prev_month_centers: dict | None = None,
                                  prev_year: str | None = None) -> tuple:
    """
    Extract one 'Historical Electricity Usage - YYYY' table from a page,
    using x-coordinates to map values to month columns.
    
    Returns: (df, month_centers, year) - the extracted dataframe, the detected month centers,
             and the year. This allows the next page to inherit month centers if needed.
    """
    img = render_page_to_image(pdf_path, page_index, dpi)
    data = pytesseract.image_to_data(img, output_type=Output.DATAFRAME)

    # basic clean-up
    data = data[(data.conf.astype(float) > 0) & data.text.notna()]
    data["text"] = data["text"].astype(str).str.strip()
    data = data[data["text"] != ""].copy()

    # derived columns
    data["cx"] = data["left"] + data["width"] / 2
    data["cy"] = data["top"] + data["height"] / 2
    data["line_id"] = list(zip(data.block_num, data.par_num, data.line_num))
    # y-coordinate based line_id for header detection (handles wrapped headers)
    data["y_line_id"] = data["top"] // LINE_GROUP_PX

    # 1) Find month header line and month column centers ----------
    month_centers = {}

    # Look for the month header line using y-coord grouping for better header detection
    best_month_line = None
    best_month_count = 0
    
    for lid, grp in data.groupby("y_line_id"):
        tokens_up = [t.upper() for t in grp["text"]]
        month_count = sum(is_month_token(t) for t in tokens_up)
        
        if month_count >= 3 and month_count > best_month_count:
            best_month_count = month_count
            best_month_line = (lid, grp)
    
    if best_month_line:
        month_header_line_id, grp = best_month_line
        # Collect all months from the header line
        for txt, cx in zip(grp["text"], grp["cx"]):
            txt_upper = txt.upper()
            if is_month_token(txt_upper):
                # Use the center x-coordinate for this token
                month_centers[txt_upper] = cx
    
    if not month_centers:
        # Try to find months across multiple lines in the header area (for wrapped headers)
        for idx, row in data.iterrows():
            if is_month_token(row["text"].upper()):
                txt_upper = row["text"].upper()
                if txt_upper not in month_centers:
                    month_centers[txt_upper] = row["cx"]
                else:
                    # Multiple instances - use the one with best visibility
                    text_series = data["text"].astype(str)
                    if row["conf"] > data[text_series.str.upper() == txt_upper]["conf"].mean():
                        month_centers[txt_upper] = row["cx"]

    header_cy = 0  # Initialize header_cy early to avoid unbound variable errors
    has_own_headers = True  # Default assumption

    if not month_centers:
        # If no month headers found on this page, try to use previous page's month centers
        # This handles multi-page tables where continuation pages don't have headers
        if prev_month_centers:
            month_centers = prev_month_centers.copy()
            # Use top of data as header_cy (no actual header on this page)
            header_cy = data["cy"].min() if len(data) > 0 else 0
            has_own_headers = False  # This is a continuation page (no own headers)
        else:
            # No month headers found and no previous page context - skip this page
            return pd.DataFrame(), {}, ""
    elif prev_month_centers and len(month_centers) < 12:
        # Use previous month centers for continuity and set header_cy to top of page
        month_centers = prev_month_centers.copy()
        header_cy = data["cy"].min() if len(data) > 0 else 0
        has_own_headers = False
    else:
        # Month headers were found on this page (complete set or no previous context)
        has_own_headers = True

    # Get header y-coordinate if we haven't set it yet
    if best_month_line and has_own_headers:
        header_y_line_id, grp = best_month_line
        header_cy = grp["cy"].mean()
    elif has_own_headers:
        # If header_cy wasn't set above (e.g., found months but not best_month_line)
        header_cy = data["cy"].min() if len(data) > 0 else 0

    # 2) Find all YEAR section headers and their positions
    # Data between "Historical Electricity Usage - YYYY" and the next year header (or end) 
    # should be assigned to YYYY
    header_year_re = re.compile(
        r"Historical\s+Electricity\s+Usage\s*-\s*(\d{4})",
        re.IGNORECASE,
    )
    
    # Find all year headers with their y-positions
    year_sections = []  # List of (y_position, year_string)
    for lid, grp in data.groupby("line_id"):
        line_text = " ".join(grp["text"])
        m = header_year_re.search(line_text)
        if m:
            cy = grp["cy"].mean()
            year_sections.append((cy, m.group(1)))
    
    # Sort by y-position (top to bottom)
    year_sections.sort()
    
    # Helper function to determine which year a row belongs to based on its y-position
    def get_year_for_position(cy_pos):
        """Returns the year for data at a given y-position"""
        if not year_sections:
            # No year sections found on this page - use previous year from previous page
            return prev_year if prev_year else ""
        
        # Check if position is before the first year header
        # If so, it's continuation data from the previous page's last section
        first_section_y, first_section_year = year_sections[0]
        if cy_pos < first_section_y:
            # Data before first section header belongs to previous year
            return prev_year if prev_year else ""
        
        # Find which year section this position belongs to
        # Data belongs to the year whose header it appears after (until the next header or end)
        for i in range(len(year_sections) - 1, -1, -1):  # Search backwards
            section_y, section_year = year_sections[i]
            if cy_pos >= section_y:
                # Position is at or after this section header
                return section_year
        
        # Fallback (should not reach here given the logic above)
        return prev_year if prev_year else ""

    # 3) Parse lines below the month header ----------
    records = []
    pending_values = {}  # Store orphan value rows to merge with next label

    for lid, grp in data.groupby("y_line_id"):  # Use y_line_id to keep rows together
        cy = grp["cy"].mean()
        if cy <= header_cy:
            continue  # only rows below month header

        # Determine the year for this row based on its position
        row_year = get_year_for_position(cy)

        grp_sorted = grp.sort_values("cx").reset_index(drop=True)
        line_text = " ".join(grp_sorted["text"]).strip()
        if not line_text:
            continue

        # stop lines outside the table
        if re.search(r"Monthly\s+totals\s+do\s+not\s+include", line_text, re.IGNORECASE):
            continue

        # ---- 3a) find first value token anywhere on the line ----
        first_val_idx = None
        for i, row in grp_sorted.iterrows():
            if is_value_token(row["text"]):
                first_val_idx = i
                break

        if first_val_idx is None:
            # Entire row is a label/section heading (no values)
            label = " ".join(grp_sorted["text"]).strip()
            
            # If we have pending orphan values, assign them to this label
            if pending_values:
                rec = {"Year": row_year, "Label": label, "Page": page_index + 1}
                for m in MONTHS_ORDER:
                    rec[m] = " ".join(pending_values.get(m, [])) if pending_values.get(m) else None
                pending_values = {}
            else:
                rec = {"Year": row_year, "Label": label, "Page": page_index + 1}
                for m in MONTHS_ORDER:
                    rec[m] = None
            records.append(rec)
            continue

        if first_val_idx == 0:
            # Row starts with value tokens and has NO label tokens
            # This is an orphan value row - collect it for the next label row
            value_tokens = grp_sorted
            
            # Map value tokens to months
            for _, w in value_tokens.iterrows():
                txt = w["text"]
                if not is_value_token(txt):
                    continue
                cx = w["cx"]
                if month_centers:
                    nearest_month = min(month_centers.keys(),
                                        key=lambda m: abs(month_centers[m] - cx))
                    if nearest_month not in pending_values:
                        pending_values[nearest_month] = []
                    pending_values[nearest_month].append(txt)
            continue

        label_tokens = grp_sorted.iloc[:first_val_idx]
        value_tokens = grp_sorted.iloc[first_val_idx:]

        label = " ".join(label_tokens["text"]).strip()

        # 3b) map numeric tokens to nearest month column by x-coordinate ----
        # Initialize with detected months only, will default to NaN for undetected
        month_values = {m: [] for m in month_centers.keys()}
        for _, w in value_tokens.iterrows():
            txt = w["text"]
            if not is_value_token(txt):
                continue
            cx = w["cx"]
            # Find nearest month by x-coordinate
            if month_centers:
                nearest_month = min(month_centers.keys(),
                                    key=lambda m: abs(month_centers[m] - cx))
                month_values[nearest_month].append(txt)

        rec = {"Year": row_year, "Label": label, "Page": page_index + 1}
        for m in MONTHS_ORDER:
            # First, use any pending orphan values from previous orphan row
            if m in pending_values and pending_values[m]:
                rec[m] = " ".join(pending_values[m])
            # Then, add any values from this row's values (these take precedence over orphans)
            elif m in month_values:
                rec[m] = " ".join(month_values[m]) if month_values[m] else None
            else:
                rec[m] = None
        records.append(rec)
        pending_values = {}  # Clear pending values after consuming them

    df = pd.DataFrame(records)
    cols = ["Year", "Label", "Page"] + MONTHS_ORDER
    df = df[cols]
    
    # Post-process: Merge orphan value rows with matching labeled rows
    # Sometimes OCR splits a row into label + orphan values on adjacent y-lines
    # when the row is taller than the y_line_id grouping (LINE_GROUP_PX pixels)
    if not df.empty:
        # Collect rows that are purely values (no label, just orphan values)
        label_series = df["Label"].fillna("").astype(str)
        orphan_mask = label_series.str.strip().eq("")
        orphan_rows = df[orphan_mask].copy()
        
        if not orphan_rows.empty:
            # For each orphan row, try to find a matching label row to merge with
            # Match by: same Year, same Page, and orphan is immediately after label
            for idx in df[orphan_mask].index:
                orphan_row = df.loc[idx]
                # Find the label row this orphan should belong to
                # Look for a row with the same Year and Page, just before this row
                candidate_idx = None
                for i in range(idx - 1, -1, -1):
                    if df.loc[i, 'Year'] == orphan_row['Year'] and df.loc[i, 'Page'] == orphan_row['Page']:
                        candidate_idx = i
                        break
                
                if candidate_idx is not None and not orphan_mask.iloc[candidate_idx]:
                    # Found a label row - merge orphan values into it
                    for month in MONTHS_ORDER:
                        orphan_val = orphan_row[month]
                        label_val = df.loc[candidate_idx, month]
                        # Fill missing values in label row with orphan values
                        if pd.isna(label_val) or label_val is None:
                            df.loc[candidate_idx, month] = orphan_val
            
            # Remove orphan rows after merging
            df = df[~orphan_mask].reset_index(drop=True)
    
    # Determine the last year found on this page to pass to next page
    last_year = year_sections[-1][1] if year_sections else (prev_year if prev_year else "")
    
    return df, month_centers, last_year


# -------------------------------------------------
# Driver: run for ALL pages
# -------------------------------------------------
def extract_all_usage_tables(pdf_path: str, dpi: int = 300) -> pd.DataFrame:
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    dfs = []
    prev_month_centers = None
    prev_year = None

    for pidx in range(n_pages):
        df_page, month_centers, year = extract_usage_table_by_coords(
            pdf_path,
            page_index=pidx,
            dpi=dpi,
            prev_month_centers=prev_month_centers,
            prev_year=prev_year,
        )
        if not df_page.empty:
            dfs.append(df_page)
            # Pass month centers and year to next page in case it's a continuation
            prev_month_centers = month_centers
            prev_year = year

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def pivot_usage_table(usage_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot the extracted table: Year stays; each Label becomes a column.
    Rows = (Year, Month). Columns = Year, Month, then Bill From, Bill To,
    Billing Days, Billed Rate (in that order if present), then all other labels.
    """
    if usage_df.empty:
        return pd.DataFrame()
    # Melt month columns to Year, Label, Month, Value
    id_vars = ["Year", "Label", "Page"]
    long = usage_df.melt(
        id_vars=id_vars,
        value_vars=MONTHS_ORDER,
        var_name="Month",
        value_name="Value",
    )
    # Pivot so each Label becomes a column; rows = (Year, Month)
    pivoted = long.pivot_table(
        index=["Year", "Month"],
        columns="Label",
        values="Value",
        aggfunc=lambda x: x.iloc[0],
    ).reset_index()
    pivoted.columns.name = None
    # Sort by Year, then by month order (JAN … DEC)
    pivoted["Month"] = pd.Categorical(pivoted["Month"], categories=MONTHS_ORDER, ordered=True)
    pivoted = pivoted.sort_values(["Year", "Month"]).reset_index(drop=True)
    pivoted["Month"] = pivoted["Month"].astype(str)  # back to string for Excel
    return pivoted



pdf_files = list(pdf_folder.glob("*.pdf"))

if not pdf_files:
    print(f"No PDF files found in {pdf_folder}")
else:
    print(f"Found {len(pdf_files)} PDF file(s) in {pdf_folder}")
    
    for pdf_path in pdf_files:
        # Extract filename without extension
        filename = os.path.splitext(os.path.basename(pdf_path))[0]
        try:
            
            print(f"Processing: {filename}.pdf")

            output_excel = output_folder / f"{filename}_extracted.xlsx"
            output_pivoted = output_folder / f"{filename}_pivoted.xlsx"
            if output_excel.exists() and output_pivoted.exists():
                print(f"Skipping: outputs already exist for {filename}.pdf")
                print()
                continue
            
            # Extract data
            usage_df = extract_all_usage_tables(str(pdf_path), dpi=DPI)
            
            if not usage_df.empty:
                # Filter out excluded labels (after parsing, before writing to excel)
                def should_keep_label(lbl):
                    if pd.isna(lbl) or lbl is None:
                        return True
                    s = str(lbl).strip()
                    return not any(
                        re.search(pat, s, re.IGNORECASE) for pat in EXCLUDED_LABEL_PATTERNS
                    )
                usage_df = usage_df[usage_df["Label"].apply(should_keep_label)].reset_index(drop=True)
                # Normalize labels that are the same in the PDF but get split/truncated by coords (e.g. On ESS -> On Peak Energy ESS)
                # usage_df["Label"] = usage_df["Label"].replace(LABEL_ALIASES)
                
                # Write main extracted table
                usage_df.to_excel(output_excel, index=False)
                print(f"Saved: {os.path.abspath(output_excel)}")
                print(f"Rows: {len(usage_df)}, Years: {usage_df['Year'].unique()}")

                # Pivot table and write second Excel (after existing file is written)
                pivoted_df = pivot_usage_table(usage_df)
                if not pivoted_df.empty:
                    pivoted_df.to_excel(output_pivoted, index=False)
                    print(f"Saved pivoted: {os.path.abspath(output_pivoted)}")
            else:
                print(f"No tables found in {filename}.pdf")
            
            print()
        
        except Exception as e:
            print(f"Error processing {filename}.pdf: {str(e)}")
            print()