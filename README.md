# VA Test Project - Electricity Tariff Billing Comparison Tool

A comprehensive Streamlit-based application for comparing electricity rate schedules from Virginia Beach (VEPGA). Analyzes customer billing history, calculates charges under different tariff schedules, and identifies potential savings.

---

## 📋 Table of Contents
- [Overview](#overview)
- [Project Structure](#project-structure)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Data Pipeline](#data-pipeline)
- [Configuration](#configuration)
- [File Guide](#file-guide)

---

## 🎯 Overview

This project helps electricity customers in Virginia Beach understand how their current charges compare to alternative VEPGA rate schedules (VE-100, VE-102, VE-110, VE-120, VE-154). It:

1. **Normalizes** billing history from raw Excel files
2. **Analyzes** usage patterns and detects anomalies
3. **Calculates** charges under 5 different rate schedules
4. **Compares** results and identifies maximum savings opportunities
5. **Visualizes** findings in an interactive web dashboard

---




## 📁 Project Structure

```
VA_test/
├── src/
│   ├── va_step1_base.py                      # 📥 Load & normalize raw data
│   ├── va_step2_anomalies.py                 # 📊 Analyze usage patterns
│   ├── riders_table_new.py                   # 🏷️  Parse rider rates
│   ├── new-bills-profile.py                  # 📋 Additional billing profile logic
│   ├── Billing Engine/
│   │   └── app_new.py                        # ⚙️  Core billing calculations
│   ├── Web_UI/
│   │   └── streamlit.py                      # 🎨 Web UI dashboard
│   └── Utils/
│       └── paths.py                          # 🔧 Configuration & file paths
│
├── data/
│   ├── raw/
│   │   └── City of VA Beach Usage History.xlsb    # Original billing data
│   ├── interim/
│   │   ├── va_step1_base_new.xlsx                 # Step 1 output
│   │   └── va_step2_anomalies.xlsx                # Step 2 output
│   ├── rider_tables/                        # Legacy rider rate files
│   ├── rider_tables_new/                     # Updated rider rate files
│   └── export/
│       └── usage_savings_output.xlsx         # Final billing comparison
│
├── test/
│   ├── app.py                                # Legacy test version
│   └── riders_table.py                       # Legacy rider parser
│
├── .git/                                     # Version control
├── .gitignore                                # Git ignore rules
├── venv/                                     # Python virtual environment
├── __pycache__/                              # Python cache
├── requirements.txt                          # Python dependencies
├── README.md                                 # This file
└── FILE_GUIDE.md                             # Detailed file documentation
```

---

## ✨ Features

### 1. **Data Normalization (va_step1_base.py)**
- Loads raw billing data from XLSB format
- Parses multiple date formats (Excel serial, timestamps, YYYYMMDD strings)
- Standardizes column names and data types
- Filters Virginia-only accounts
- Calculates billing gaps (days between consecutive bills)
- **Output:** `va_step1_base_new.xlsx`

### 2. **Anomaly Analysis (va_step2_anomalies.py)**
- Year-over-Year (YoY) usage comparisons
- Spike detection and anomaly flags
- 12-month rolling summaries per account
- Identifies accounts with high demand variability
- **Output:** `va_step2_anomalies.xlsx`

### 3. **Billing Engine (app_new.py)**
Five schedule calculation functions:

#### **Schedule 120 (VE-120)** — Small Commercial Non-Demand
- Non-metered accounts only
- Seasonal ES rates (On-peak / Off-peak blend)
- Fixed customer charge + distribution + ES + riders
- No demand charge

#### **Schedule 154 (VE-154)** — Small Commercial Single-Rate
- Metered or unmetered
- Flat ES rate (no seasonality)
- Fixed customer charge + distribution + ES + riders

#### **Schedule 102 (VE-102)** — Small Commercial Tiered
- **Unmetered if:** any monthly usage ≤ 49 kWh in last 12 months
- **Metered otherwise**
- Per-kWh charges vary by usage tier

#### **Schedule 100 (VE-100)** — Large Commercial Non-Demand
- **Non-Demand if:** all monthly usage < 10,000 kWh in last 12 months
- Tiered ES buckets (150 kWh per tier, up to 4 tiers)
- Seasonal rates where applicable
- kW riders suppressed for Non-Demand accounts

#### **Schedule 110 (VE-110)** — Large Commercial Demand
- **Non-Demand if:** all monthly usage < 10,000 kWh in last 12 months
- Demand-based billing with kW charges
- Tiered ES buckets
- Full rider charges (per-kWh + per-kW)

**Output:** 8 columns per schedule:
- `ve{X00}_calculated_amount` — Total charge
- `ve{X00}_savings` — Current charge − calculated charge
- `ve{X00}_case_type` — Whether schedule matches current rate
- Parameter columns (customer charge, dist rate, ES rates, riders)

### 4. **Interactive Dashboard (streamlit.py)**
- Browse 12-month account history
- Compare current vs. proposed schedules
- View calculated vs. actual charges
- Export comparison to Excel
- **Run:** `streamlit run src/Web_UI/streamlit.py`

### 5. **Rider Management (riders_table_new.py)**
- Parses surcharge/rider rate tables
- Normalizes money string formats ('$0.014945', '($0.25)', 'N/A')
- Extracts per-kWh and per-kW components
- Used by all schedule functions

---

## 🚀 Installation

### Prerequisites
- Python 3.8+
- macOS, Linux, or Windows

### Setup

1. **Clone/navigate to project:**
```bash
cd /Users/patil/Library/CloudStorage/OneDrive-UniversityatBuffalo/Desktop/MS/2.Course/Project/VA_test
```

2. **Create virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

### Key Dependencies
- `pandas` — Data manipulation
- `openpyxl`, `pyxlsb` — Excel I/O (XLSX, XLSB)
- `streamlit` — Web dashboard
- `numpy` — Numeric operations

---

## ⚡ Quick Start

### 1. Prepare Data
Ensure these files exist:
- `data/raw/City of VA Beach Usage History.xlsb` — Original billing data
- `data/raw/Mini_Edit_VEPGA_Schedules_Compact.xlsx` — Rate parameters (schedule definitions)
- `data/rider_tables/[rider files]` — Rider rates

### 2. Run Data Pipeline

**Step 1: Normalize raw data**
```bash
python src/va_step1_base.py
# → Creates: data/interim/va_step1_base_new.xlsx
```

**Step 2: Analyze usage patterns**
```bash
python src/va_step2_anomalies.py
# → Creates: data/interim/va_step2_anomalies.xlsx
```

**Step 3: Calculate billing comparisons**
```bash
python src/Billing\ Engine/app_new.py
# → Creates: data/export/usage_savings_output.xlsx
```

### 3. View Results
```bash
streamlit run src/Web_UI/streamlit.py
```
Opens interactive dashboard at `http://localhost:8501`

---

## �📊 Data Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Raw Input: data/raw/City of VA Beach Usage History.xlsb         │
│ + Schedules: data/raw/Mini_Edit_VEPGA_Schedules_Compact.xlsx    │
│ + Riders: data/rider_tables_new/[rider tables]                  │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
        ┌─────────────────────────────┐
        │  STEP 1: va_step1_base.py   │
        │  - Load + normalize dates   │
        │  - Standardize columns      │
        │  - Filter VA accounts       │
        │  - Calculate gaps           │
        └────────────┬────────────────┘
                     ↓
        [va_step1_base_new.xlsx]
                     ↓
        ┌─────────────────────────────┐
        │ STEP 2: va_step2_anomalies  │
        │  - Add YoY analysis         │
        │  - Detect anomalies/spikes  │
        │  - 12-month summaries       │
        └────────────┬────────────────┘
                     ↓
        [va_step2_anomalies.xlsx]
                     ↓
        ┌──────────────────────────────────────┐
        │  STEP 3: app_new.py (Billing Engine) │
        │  ┌────────────────────────────────┐  │
        │  │ schedule_120() — VE-120        │  │
        │  │ schedule_154() — VE-154        │  │
        │  │ schedule_102() — VE-102        │  │
        │  │ schedule_100() — VE-100        │  │
        │  │ schedule_110() — VE-110        │  │
        │  └────────────────────────────────┘  │
        │  Per-row: cust + dist + ES + riders  │
        │  Calculate savings vs. current       │
        └────────────┬───────────────────────┘
                     ↓
        [usage_savings_output.xlsx]
        (All schedules side-by-side)
                     ↓
        ┌─────────────────────────────┐
        │  STEP 4: streamlit.py       │
        │  - Load comparison output   │
        │  - Interactive dashboard    │
        │  - Export to Excel          │
        └─────────────────────────────┘
```

---

## 🔧 Configuration

Edit [src/Utils/paths.py](src/Utils/paths.py) to set:

```python
SCHEDULES_XLSX = "path/to/Mini_Edit_VEPGA_Schedules_Compact.xlsx"
USAGE_INT = "path/to/va_step1_base_new.xlsx"
RIDERS_OUT = "path/to/rider_rates.xlsx"
EXPORT_DIR = "path/to/data/export/"
```

Paths default to:
```
data/raw/Mini_Edit_VEPGA_Schedules_Compact.xlsx
data/interim/va_step1_base_new.xlsx
data/rider_tables_new/[rider file]
data/export/
```

### Airflow config and secrets

- `infra/airflow/config/airflow.cfg` is committed for reproducible non-secret defaults.
- Secrets and credentials must be set in `.env` (ignored by git).
- Start from `.env.example`:

```bash
cp .env.example .env
```

Required Airflow variables in `.env`:

- `AIRFLOW__CORE__FERNET_KEY`
- `AIRFLOW__API__SECRET_KEY`
- `AIRFLOW__API_AUTH__JWT_SECRET`
- `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`
- `AIRFLOW__CELERY__RESULT_BACKEND`
- `AIRFLOW__CELERY__BROKER_URL`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

For local development, Airflow reads values from `.env` via `infra/airflow/docker-compose.yaml`, and env vars override `airflow.cfg`.

---

## 📄 File Guide

See `FILE_GUIDE.md` for detailed documentation of:
- File purposes and responsibilities
- Column definitions and schemas
- Excel sheet structures
- Parameter extraction logic
- Implementation notes and caveats

### Key Files

| File | Purpose |
|------|---------|
| [src/va_step1_base.py](src/va_step1_base.py) | Load XLSB, normalize dates/columns, filter VA, output base table |
| [src/va_step2_anomalies.py](src/va_step2_anomalies.py) | Add YoY analysis, anomaly detection, 12-month summaries |
| [src/new-bills-profile.py](src/new-bills-profile.py) | Additional billing profile analysis |
| [src/Billing Engine/app_new.py](src/Billing\ Engine/app_new.py) | Calculate charges for 5 schedules, compare vs. current, compute savings |
| [src/Web_UI/streamlit.py](src/Web_UI/streamlit.py) | Interactive dashboard: browse accounts, compare schedules, export |
| [src/riders_table_new.py](src/riders_table_new.py) | Parse rider rates, normalize money formats |
| [src/Utils/paths.py](src/Utils/paths.py) | Centralized configuration and file paths |

---

## ⚙️ Implementation Details

### Billing Type Logic
- **VE-102 (Unmetered):** Any month in last 12m with usage ≤ 49 kWh
- **VE-100/110 (Non-Demand):** All months in last 12m with usage < 10,000 kWh

### ES Charge Calculation
- **Non-Demand:** Flat per-kWh rate (seasonal blend where applicable)
- **Demand:** Tiered buckets (150 kWh per bucket) across 4 tiers, seasonal

### Rider Handling
- **Per-kWh:** Applied to all account types
- **Per-kW:** Applied only to Demand accounts (set to 0 for Non-Demand)

### Parameter Extraction
All parameters (customer charge, dist rate, ES rates, riders) extracted from Excel via:
- Sheet name (e.g., "Schedule 120")
- Column values: Category, Sub-Category, Item, Condition/Tier
- **Format changes in Excel will break lookups** — validate before processing

---

## 🐛 Troubleshooting

### "Import src.paths could not be resolved"
- Ensure `src/__init__.py` exists
- Add workspace folder to `python.analysis.extraPaths` in VS Code settings

### XLSB read errors
- Install: `pip install pyxlsb`
- Verify file is not corrupted

### Missing parameter errors
- Validate Excel sheet structure matches expected columns
- Check Category, Sub-Category, Item, Condition/Tier values

### Streamlit not loading
- Run: `streamlit run src/Web_UI/streamlit.py` from project root
- Check output path exists: `data/export/usage_savings_output.xlsx`

---

## 📈 Next Steps

- [ ] Add unit tests for schedule functions
- [ ] Implement batch processing for large datasets
- [ ] Add data validation checks
- [ ] Export comparison reports as PDF
- [ ] Add forecast/projection features

---

## 📞 Support

For questions or issues, refer to:
- `FILE_GUIDE.md` — Detailed file and data structure documentation
- Comments in source files (marked with `#`)
- Excel parameter sheets — Verify rate/schedule definitions
