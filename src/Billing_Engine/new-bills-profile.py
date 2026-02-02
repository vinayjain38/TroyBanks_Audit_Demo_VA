# @title New Format - Only Pg 2 - Tesseract OCR & Splitting Pattern - Success

# --- Install dependencies ---
# pip install pymupdf pillow pytesseract python-dotenv

import re
import os
import io
import sys
import fitz
import pytesseract
import pandas as pd
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

# --- DYNAMIC ROOT RESOLUTION ---
# Assuming file is in src/scripts/new-bills-profile.py
PROJECT_ROOT = Path(__file__).resolve().parents[2] 
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from root
load_dotenv(PROJECT_ROOT / ".env")

# --- TESSERACT CONFIGURATION ---
tesseract_path = os.getenv("TESSERACT_PATH", "").strip('"').strip()

if tesseract_path and os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    print(f"Using Tesseract from .env: {tesseract_path}")
else:
    # Fallback: Try to find 'tesseract' in the system PATH
    import shutil
    system_tess = shutil.which("tesseract")
    if system_tess:
        pytesseract.pytesseract.tesseract_cmd = system_tess
        print(f"TESSERACT_PATH not in .env. Using system default: {system_tess}")
    else:
        print("CRITICAL: Tesseract not found. Please install Tesseract and update .env")

# --- PATH CONFIGURATION ---
PDF_DIR = PROJECT_ROOT / "data" / "new-bills"
EXCEL_OUTPUT_DIR = PROJECT_ROOT / "data" / "interim" / "new-bills-profile"
EXCEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ... (rest of your parsing logic remains the same) ...


# # Set Tesseract path
# tesseract_path = os.getenv("TESSERACT_PATH", "").strip('"').strip()
# tessdata_prefix = os.getenv("TESSDATA_PREFIX", "").strip('"').strip()

# if tesseract_path:
#     # Use absolute path
#     tesseract_path = os.path.abspath(tesseract_path)
    
#     # Get directory of tesseract executable
#     tesseract_dir = os.path.dirname(tesseract_path)
    
#     # Add tesseract directory to PATH so subprocess can find it
#     os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")
    
#     # Set pytesseract to use tesseract executable name (it will find it in PATH)
#     pytesseract.pytesseract.pytesseract_cmd = "tesseract.exe"
    
#     print(f"Using Tesseract from: {tesseract_dir}")
    
#     # Verify the file exists
#     if not os.path.exists(tesseract_path):
#         raise FileNotFoundError(f"Tesseract not found at: {tesseract_path}")
# else:
#     raise RuntimeError("TESSERACT_PATH must be set in .env file")

# if tessdata_prefix:
#     tessdata_prefix = os.path.abspath(tessdata_prefix)
#     os.environ["TESSDATA_PREFIX"] = tessdata_prefix
#     print(f"Using TESSDATA: {tessdata_prefix}")

# BASE_DIR = Path(__file__).parent.parent
# PDF_DIR = BASE_DIR / "data" / "new-bills"

# Output directories
# EXCEL_OUTPUT_DIR = BASE_DIR / "data" / "interim" / "new-bills-profile"
# EXCEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


PAGE_INDEX = 1                             # 0-based index ⇒ 1 = page 2
DPI = 400

def ocr_pdf_page(pdf_path, page_index: int, dpi: int = 400) -> str:
    """Render one PDF page as image and return OCR text."""
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))

    try:
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(f"PDF has {len(doc)} pages, but page_index {page_index} was given")

        page = doc[page_index]

        # Render image
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # PyMuPDF → PIL
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # OCR
        text = pytesseract.image_to_string(img)
        return text
    finally:
        doc.close()


def parse_dominion_account_profile(ocr_text: str):
    # Work on raw lines, keep blanks
    lines = [l.rstrip() for l in ocr_text.splitlines()]

    def find_index(text):
        for i, l in enumerate(lines):
            if l.strip() == text:
                return i
        return None

    # 1) Account Profile: value is next non-empty line
    acc_idx = find_index("Account Profile")
    acc_value = ""
    if acc_idx is not None:
        for j in range(acc_idx + 1, len(lines)):
            if lines[j].strip():
                acc_value = lines[j].strip()
                break

    # 2) Column labels (left column)
    column_labels_full = [
        "Phone Number",
        "Mailing Address",
        "Customer Class",
        "ACCOUNT NO.",
        "Service Address",
        "Turn On Date",
        "District Office",
        "Tax District",
        "NAICS Code",
        "Meter Number(s)",
        "Current Rate",
        "Voltage",
        "Delivery Phase",
        "Minimum Demand",
        "Facility Charge",
        "Billing Status",
    ]

    label_indices = {}
    for lbl in column_labels_full:
        idx = find_index(lbl)
        if idx is not None:
            label_indices[lbl] = idx

    # 3) Values column: from after "Billing Status" to 'Active'/'Inactive'
    billing_idx = label_indices.get("Billing Status", None)
    if billing_idx is None:
        raise RuntimeError("Could not find 'Billing Status' in OCR text.")

    status_idx = None
    for i in range(billing_idx + 1, len(lines)):
        val = lines[i].strip()
        if val in ("Active", "Inactive"):
            status_idx = i
            break
    if status_idx is None:
        raise RuntimeError("Could not find 'Active' or 'Inactive' after 'Billing Status'.")

    value_zone = lines[billing_idx + 1 : status_idx + 1]
    value_lines = [l.strip() for l in value_zone if l.strip()]

    # ------------------------------------------------------------------
    # VARIABLE-LENGTH SPLITTING USING PATTERNS
    # ------------------------------------------------------------------

    # value_lines[0] should always be the phone line
    phone_line = value_lines[0] if value_lines else ""

    # Find ACCOUNT NO. line: numeric-only, no letters, and skip index 0 (phone)
    acc_no_idx = None
    for i in range(1, len(value_lines)):  # start from 1 to skip phone
        v = value_lines[i]
        only_digits = re.sub(r"\D", "", v)
        if len(only_digits) >= 6 and not any(c.isalpha() for c in v):
            acc_no_idx = i
            break
    if acc_no_idx is None:
        raise RuntimeError("Could not detect ACCOUNT NO. line in value column.")

    # Turn On Date: first line after account no with month name + year
    month_names = [
        "January","February","March","April","May","June",
        "July","August","September","October","November","December"
    ]
    def looks_like_date(s: str) -> bool:
        return any(m in s for m in month_names) and re.search(r"\b\d{4}\b", s) is not None

    date_idx = None
    for i in range(acc_no_idx + 1, len(value_lines)):
        if looks_like_date(value_lines[i]):
            date_idx = i
            break
    if date_idx is None:
        raise RuntimeError("Could not detect Turn On Date line in value column.")

    # Customer class: last non-empty line before account number
    customer_idx = None
    for i in range(acc_no_idx - 1, 0, -1):
        if value_lines[i].strip():
            customer_idx = i
            break
    if customer_idx is None or customer_idx <= 0:
        raise RuntimeError("Customer class index invalid based on ACCOUNT NO. position.")

    # Mailing address: lines between phone and customer class
    mailing_lines  = value_lines[1:customer_idx]               # 1 or more lines
    customer_line  = value_lines[customer_idx]
    account_line   = value_lines[acc_no_idx]
    service_lines  = value_lines[acc_no_idx + 1 : date_idx]    # 1 or more lines
    turn_on_line   = value_lines[date_idx]

    # Tail after Turn On Date: single-line items in fixed order
    tail = value_lines[date_idx + 1:]
    def tail_get(i):
        return tail[i] if i < len(tail) else ""

    district_line     = tail_get(0)
    meter_line        = tail_get(1)
    current_rate_line = tail_get(2)
    voltage_line      = tail_get(3)
    phase_line        = tail_get(4)
    min_demand_line   = tail_get(5)
    facility_line     = tail_get(6)
    status_line       = tail_get(7)

    # ------------------------------------------------------------------
    # BUILD FINAL PAIRS
    # ------------------------------------------------------------------
    all_labels = [
        "Account Profile",
        "Phone Number",
        "Mailing Address",
        "Customer Class",
        "ACCOUNT NO.",
        "Service Address",
        "Turn On Date",
        "District Office",
        "Tax District",
        "NAICS Code",
        "Meter Number(s)",
        "Current Rate",
        "Voltage",
        "Delivery Phase",
        "Minimum Demand",
        "Facility Charge",
        "Billing Status",
        "Key Account Manager",
        "Dominion Energy",
        "Image text",
    ]
    pairs = {lbl: "" for lbl in all_labels}

    pairs["Account Profile"] = acc_value
    pairs["Phone Number"]    = phone_line
    pairs["Mailing Address"] = " ".join(mailing_lines).strip()
    pairs["Customer Class"]  = customer_line
    pairs["ACCOUNT NO."]     = account_line
    pairs["Service Address"] = " ".join(service_lines).strip()
    pairs["Turn On Date"]    = turn_on_line
    pairs["District Office"] = district_line
    # Tax District, NAICS Code remain empty
    pairs["Meter Number(s)"] = meter_line
    pairs["Current Rate"]    = current_rate_line
    pairs["Voltage"]         = voltage_line
    pairs["Delivery Phase"]  = phase_line
    pairs["Minimum Demand"]  = min_demand_line
    pairs["Facility Charge"] = facility_line
    pairs["Billing Status"]  = status_line

    # ------------------------------------------------------------------
    # Key Account Manager, Dominion Energy, Image text (same idea as before)
    # ------------------------------------------------------------------

    # Key Account Manager: person name above label
    kam_idx = find_index("Key Account Manager")
    if kam_idx is not None:
        name = ""
        for j in range(kam_idx - 1, -1, -1):
            cand = lines[j].strip()
            if not cand:
                continue
            # Generic noise filtering
            if cand.startswith("©"):                 # copyright/footer
                continue
            if cand in ("Dominion", "Energy’"):      # logo pieces
                continue
            if "Page" in cand and "of" in cand:      # footer page indicator
                continue
            if "Dominion Energy" in cand and "Office" in cand:   # address block
                continue
            name = cand
            break
        pairs["Key Account Manager"] = name

    # Dominion Energy: address after label
    dom_idxs = [i for i, l in enumerate(lines) if l.strip() == "Dominion Energy"]
    dom_idx = None
    if dom_idxs:
        if kam_idx is not None:
            for i in dom_idxs:
                if i > kam_idx:
                    dom_idx = i
                    break
        if dom_idx is None:
            dom_idx = dom_idxs[-1]

    if dom_idx is not None:
        addr = []
        for j in range(dom_idx + 1, len(lines)):
            cand = lines[j].strip()
            if cand.startswith("Year Total") or "kWh" in cand or cand.startswith("Average costs"):
                break
            if cand:
                addr.append(cand)
        pairs["Dominion Energy"] = " ".join(addr)

    # Image text: logo "Dominion Energy'"
    img_text = ""
    for i, l in enumerate(lines[:-1]):
        if l.strip() == "Dominion" and lines[i + 1].strip() == "Energy’":
            img_text = "Dominion Energy'"
            break
    if not img_text:
        for j in range(len(lines) - 1, -1, -1):
            cand = lines[j].strip()
            if cand:
                img_text = cand
                break
    pairs["Image text"] = img_text

    return [(lbl, pairs[lbl]) for lbl in all_labels]


# Find all PDFs in the directory
pdf_files = sorted(PDF_DIR.glob("*.pdf"))
if not pdf_files:
    raise FileNotFoundError(f"No PDF files found in {PDF_DIR}")

print(f"Found {len(pdf_files)} PDF(s) in {PDF_DIR}")
print("=" * 60)

# Process each PDF
for pdf_path in pdf_files:
    pdf_name = pdf_path.stem  # Get filename without extension (e.g., "Profile0412")
    
    print(f"\nProcessing: {pdf_path.name}...")
    
    # Generate dynamic output paths based on PDF name
    OUTPUT_EXCEL = EXCEL_OUTPUT_DIR / f"{pdf_name}_page2_parsed.xlsx"
    
    # Extract OCR text
    ocr_text = ocr_pdf_page(pdf_path, PAGE_INDEX, DPI).strip()

    print(f"  OCR complete.")

    # Parse the extracted text
    print("  Parsing account profile...")
    pairs = parse_dominion_account_profile(ocr_text)

    # Print results
    print(f"  {'='*50}")
    print(f"  {pdf_name} - Account Profile")
    print(f"  {'='*50}")
    for label, value in pairs:
        if value:  # Only print non-empty values
            print(f"    {label:23} -> {value}")

    # Save to Excel
    df = pd.DataFrame(pairs, columns=["Label", "Value"])
    df.to_excel(str(OUTPUT_EXCEL), index=False)

    print(f"  Excel saved to: {OUTPUT_EXCEL}")

print("\n" + "=" * 60)
print("All PDFs processed successfully!")