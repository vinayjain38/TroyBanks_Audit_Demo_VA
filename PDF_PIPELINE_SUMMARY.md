# PDF Upload & Processing Pipeline - Summary

## ✅ YES - A Complete Pipeline EXISTS

Your project has a **full end-to-end pipeline** that handles PDF uploads, extracts billing data, and calculates charges under different tariff schedules.

---

## 📊 Pipeline Architecture

### **Stage 1: PDF Upload & OCR Extraction**
**Files:** 
- [src/Billing_Engine/new-bills_v2.py](src/Billing_Engine/new-bills_v2.py) — Main PDF parser
- [src/Billing_Engine/new-bills-profile.py](src/Billing_Engine/new-bills-profile.py) — Account profile extraction

**How it works:**
1. PDFs placed in `data/new-bills/` directory
2. Uses **PyMuPDF** (fitz) to render PDF pages as images at 400 DPI
3. Uses **Tesseract OCR** to extract text from images
4. Parses **historical electricity usage tables** by:
   - Detecting month headers (JAN-DEC) by x-coordinates
   - Grouping text into lines by y-coordinates
   - Mapping values to months based on spatial proximity
   - Handling multi-page tables with year continuity
5. Extracts **account profile details** (phone, address, account #, current rate, etc.)

**Output:**
- `data/interim/new-bills-parsed/` — Two Excel files per PDF:
  - `{filename}_extracted.xlsx` — Raw extracted table (one row per label)
  - `{filename}_pivoted.xlsx` — Pivoted table (rows = months, columns = billing items)
- `data/interim/new-bills-profile/` — Account profile as Excel (one label-value pair per row)

---

### **Stage 2: Billing Engine Calculations**
**File:** [src/Billing_Engine/app_new.py](src/Billing_Engine/app_new.py)

**How it works:**
1. Loads the pivoted usage Excel from Stage 1
2. Normalizes column names to standard format:
   - `Total Consumption` → `usage_kwh`
   - `** Total Charges` → `charges`
   - `Billed Rate` → `current_rate`
   - `Demand` → `demand_kw`
3. For each of 5 schedules (VE-100, VE-102, VE-110, VE-120, VE-154):
   - Extracts rate parameters from `Mini_Edit_VEPGA_Schedules_Compact.xlsx`
   - Determines billing type (Non-Demand vs Demand) using 12-month usage rules
   - Calculates per-row charges:
     - **Customer charge** (metered/unmetered or demand/non-demand)
     - **Distribution charge** = distribution_rate × usage_kwh
     - **ES (Electricity Supply) charge** — flat rate (Non-Demand) or tiered by 150-kWh buckets (Demand)
     - **Rider charges** = usage_kwh × rider_per_kwh + demand_kw × rider_per_kw
   - Computes **savings** = current_charges − calculated_charges

**Output:**
- `data/export/usage_savings_output.xlsx` — Combined results with all schedules side-by-side

---

### **Stage 3: Pipeline Orchestration**
**File:** [src/Billing_Engine/run_new_bills_pipeline.py](src/Billing_Engine/run_new_bills_pipeline.py)

**Runs both stages automatically:**
```
Stage 1: new_bills_v2.main()     # PDF → Excel
Stage 2: app_new.main()          # Excel → Calculations
```

---

## 🚀 How to Use the Pipeline

### **Step 1: Place PDFs**
```bash
# Copy your billing PDF files to:
data/new-bills/
```

### **Step 2: Configure Tesseract (if not installed)**
Create a `.env` file in the project root:
```
TESSERACT_PATH="/usr/local/bin/tesseract"
TESSDATA_PREFIX="/usr/local/share/tessdata"
```

Alternatively, install Tesseract system-wide:
- **macOS:** `brew install tesseract`
- **Ubuntu:** `sudo apt-get install tesseract-ocr`
- **Windows:** Download from https://github.com/UB-Mannheim/tesseract/wiki

### **Step 3: Run the Pipeline**
```bash
cd /Users/jajula/Desktop/TroyBanks_Audit_Demo_VA-main
python src/Billing_Engine/run_new_bills_pipeline.py
```

Or run stages separately:
```bash
# Stage 1 only: PDF → Excel
python src/Billing_Engine/new-bills_v2.py

# Stage 2 only: Excel → Calculations
python src/Billing_Engine/app_new.py
```

### **Step 4: View Results**
Check the output files:
- **Extracted usage data:** `data/interim/new-bills-parsed/`
- **Final calculations:** `data/export/usage_savings_output.xlsx`

---

## 📋 Key Components

### **Required Dependencies**
```
PyMuPDF>=1.20.0          # PDF rendering
pytesseract>=0.3.0       # OCR
Pillow>=9.0.0            # Image processing
pandas>=2.0.0            # Data processing
openpyxl>=3.0.0          # Excel I/O
xlsxwriter>=3.0.0        # Excel writing
python-dotenv>=1.0.0     # Environment config
```

### **Data Files Required**
- **Schedule parameters:** `data/schedules/Mini_Edit_VEPGA_Schedules_Compact.xlsx`
  - Sheets: VE-100, VE-102, VE-110, VE-120, VE-154
  - Columns: Category, Sub-Category, Item, Condition/Tier, Rate

- **Rider rates:** `data/rider_tables_new/` (Excel files with surcharge data)

- **Input PDFs:** `data/new-bills/` (user-uploaded billing statements)

---

## 🛠️ Configuration & Customization

### **Tesseract OCR Settings**
**File:** [src/Billing_Engine/new-bills_v2.py](src/Billing_Engine/new-bills_v2.py#L50-L100)

Adjustable parameters:
- `DPI = 400` — Image resolution (higher = slower but more accurate)
- `LINE_GROUP_PX = 20` — Vertical pixel threshold for grouping text into lines
- `EXCLUDED_LABEL_PATTERNS` — Regex patterns to skip rows (e.g., footnotes)
- `TESSERACT_CONFIG` — Advanced Tesseract options (e.g., language, page segmentation mode)

### **Schedule Calculation Logic**
**File:** [src/Billing_Engine/app_new.py](src/Billing_Engine/app_new.py)

Key functions:
- `load_usage()` — Normalizes pivoted Excel to standard schema
- `schedule_100()`, `schedule_102()`, `schedule_110()`, `schedule_120()`, `schedule_154()` — Per-schedule calculations
- `_parse_money_series()` — Converts "$1,234.50" format to numeric values

---

## 📊 Data Flow Diagram

```
User PDFs (data/new-bills/)
       ↓
[Stage 1: new-bills_v2.py]
  - Render PDF pages to images
  - OCR extraction
  - Parse usage tables by coordinates
  - Pivot by Year & Month
       ↓
Pivoted Excel (data/interim/new-bills-parsed/)
       ↓
[Stage 2: app_new.py]
  - Load pivoted usage
  - Load rate schedule parameters
  - Determine billing type (Non-Demand/Demand)
  - Calculate charges under 5 schedules
  - Compute savings
       ↓
Output (data/export/usage_savings_output.xlsx)
  - Columns: VE-100, VE-102, VE-110, VE-120, VE-154
  - Per-row calculated amounts & savings
```

---

## ⚠️ Known Limitations & Caveats

1. **OCR Accuracy:** Depends on PDF quality and font clarity
   - Scanned/low-quality PDFs may have errors
   - Handwritten or unusual fonts not supported

2. **Table Format:** Assumes standard Dominion Energy billing format
   - Table headers must contain month abbreviations
   - Year headers format: "Historical Electricity Usage - YYYY"
   - Coordinate-based extraction may fail if table layout changes

3. **Parameter Extraction:** Relies on specific Excel column/row names
   - Format changes in `Mini_Edit_VEPGA_Schedules_Compact.xlsx` will break lookups
   - Must maintain exact column names: Category, Sub-Category, Item, Condition/Tier, Rate

4. **File Handling:**
   - Output file (`usage_savings_output.xlsx`) is **overwritten** after each pipeline run
   - No timestamp versioning by default

5. **System Requirements:**
   - **Tesseract** must be installed system-wide or configured in `.env`
   - Python 3.7+ required
   - ~100-200MB RAM for typical PDF processing

---

## 🔍 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Tesseract not found** | Install: `brew install tesseract` or configure `.env` |
| **No tables extracted** | Check PDF format matches expected Dominion template |
| **OCR text is garbled** | Increase DPI (slower) or check PDF quality |
| **Schedule calculations fail** | Verify `Mini_Edit_VEPGA_Schedules_Compact.xlsx` exists and has correct sheet names |
| **Wrong column names after pivoting** | Check PDF billing format; may need custom column mapping in `load_usage()` |

---

## 📝 Next Steps

**To add PDF upload UI:**
1. Add Streamlit file upload widget to [src/Web_UI/streamlit.py](src/Web_UI/streamlit.py)
2. Save uploaded PDF to `data/new-bills/`
3. Trigger pipeline: call `new_bills_v2.main()` and `app_new.main()`
4. Display results in UI

**Example Streamlit code:**
```python
uploaded_file = st.file_uploader("Upload billing PDF", type="pdf")
if uploaded_file:
    pdf_path = Path("data/new-bills") / uploaded_file.name
    pdf_path.write_bytes(uploaded_file.getbuffer())
    
    # Run pipeline
    from src.Billing_Engine import new_bills_v2, app_new
    new_bills_v2.main()
    app_new.main()
    
    st.success("Pipeline complete!")
```

---

## 📚 Reference

- **PyMuPDF docs:** https://pymupdf.readthedocs.io/
- **Tesseract docs:** https://github.com/tesseract-ocr/tesseract/wiki
- **Streamlit upload:** https://docs.streamlit.io/library/api-reference/widgets/st.file_uploader
