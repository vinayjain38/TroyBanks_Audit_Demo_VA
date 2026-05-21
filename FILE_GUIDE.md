# VA Test Project - File Guide


---

<a id="fileguide-contents"></a>

---

## Contents

---


- [Project Structure Overview](#fileguide-project-structure-overview)
- [Core Files](#fileguide-core-files)
  - [src/Billing engine/app_new.py](#fileguide-billing-engine-app-new)
  - [src/Web_UI/streamlit.py](#fileguide-web-ui-streamlit)
  - [frontend/streamlit3.py](#fileguide-frontend-streamlit3)
  - [src/riders_table_new.py](#fileguide-riders-table-new)
  - [src/va_step1_base.py](#fileguide-va-step1-base)
  - [src/va_step2_anomalies.py](#fileguide-va-step2-anomalies)
  - [src/Configuration_and_paths/paths.py](#fileguide-paths)
- [Data Files](#fileguide-data-files)
  - [data/raw/](#fileguide-data-raw)
  - [data/interim/](#fileguide-data-interim)
  - [data/export/](#fileguide-data-export)
  - [data/schedules/](#fileguide-data-schedules)
  - [data/rider_tables/ & data/rider_tables_new/](#fileguide-rider-tables)
- [Test Files](#fileguide-test-files)
  - [test/app.py](#fileguide-test-app)
  - [test/riders_table.py](#fileguide-test-riders-table)
- [Configuration Files](#fileguide-configuration-files)
- [Data Flow](#fileguide-data-flow)
- [Key Implementation Notes](#fileguide-key-implementation-notes)
  - [Billing Type Determination](#fileguide-billing-type-determination)
  - [ES Charge Logic](#fileguide-es-charge-logic)
  - [Parameter Extraction](#fileguide-parameter-extraction)
  - [Rider Handling](#fileguide-rider-handling)
  - [Output Behavior](#fileguide-output-behavior)
- [Quick Start](#fileguide-quick-start)

---

<a id="fileguide-project-structure-overview"></a>

---

## Project Structure Overview

---


A Streamlit-based electricity tariff billing comparison tool for Virginia Beach (VEPGA rate schedules).

---

<a id="fileguide-core-files"></a>

---

## Core Files

---


<a id="fileguide-billing-engine-app-new"></a>

### src/Billing engine/app_new.py

**Purpose:** Billing engine & core logic

- Loads customer usage history (va_step1_base.xlsx) and rider (surcharge) data
- Implements schedule calculation functions: schedule_120(), schedule_154(), schedule_102(), schedule_100(), schedule_110()
- Each schedule extracts parameters from Excel sheets: customer charge, distribution rate, ES (electricity supply) rates, and riders
- Calculates per-row charges:
  - Customer charge (metered/unmetered or demand/non-demand variant)
  - Distribution charge = dist_rate × usage_kwh
  - ES charge (flat rate for Non-Demand; tiered 150-kWh buckets for Demand, seasonal where applicable)
  - Rider charge = usage_kwh × rider_per_kwh + demand_kw × rider_per_kw (kW component suppressed for Non-Demand where required)
- Determines billing type per account (Non-Demand vs Demand) using 12-month usage rules:
  - Schedule 102: Unmetered if any monthly usage ≤ 49 kWh
  - Schedule 100/110: Non-Demand if all months in last 12m < 10,000 kWh
- Compares calculated amount vs. current charges to compute savings
- **Input:** usage_df (normalized usage data), riders_df (normalized rider rates)
- **Output:** DataFrame columns per schedule: ve{X00}_calculated_amount, ve{X00}_savings, ve{X00}_case_type, plus parameter columns
- **Note:** Writes OUTPUT_PATH (usage_savings_output.xlsx) after each schedule; file is overwritten (not appended)

<a id="fileguide-web-ui-streamlit"></a>

### src/Web_UI/streamlit.py

**Purpose:** Older local-only Web UI for browsing and comparing billing

- Streamlit app that displays last 12 months of usage data
- Allows user to select account and rate schedule
- Tab 1: Shows account details with historical billing
- Tab 2: Compares current charges vs. selected schedule charges
- Excel export feature: Downloads 12-month comparison
- **Entry point:** `streamlit run src/Web_UI/streamlit.py`

<a id="fileguide-frontend-streamlit3"></a>

### frontend/streamlit3.py

**Purpose:** Current Streamlit UI used by the Docker/backend split-stack

- Frontend app that talks to the backend API for calculation and upload workflows
- Preferred production path for Docker deployments
- **Entry point:** `streamlit run frontend/streamlit3.py`

<a id="fileguide-riders-table-new"></a>

### src/riders_table_new.py

**Purpose:** Parse and prepare rider (surcharge) data

- Loads rider rate tables from Excel (RIDERS_OUT)
- Normalizes columns:
  - schedule_code from 'RATE SCHEDULE' column
  - rider_total_per_kwh from 'AGGREGATE RIDER ADJUSTMENT PER KWH' (converts '$0.014945' format to float)
  - rider_total_per_kw from 'AGGREGATE RIDER ADJUSTMENT PER KW'
- Uses _parse_money_series() helper to convert money strings ('$1,234.50', '($0.25)', 'N/A') to numeric values
- **Output:** riders_df used by schedule functions in app_new.py

<a id="fileguide-va-step1-base"></a>

### src/va_step1_base.py

**Purpose:** Data preparation - Step 1

- Loads raw billing data from City of VA Beach usage history file
- Normalizes dates (handles Excel serial dates, timestamps, strings)
- Cleans and standardizes column names and data types
- Ensures required columns exist: usage_kwh, charges, current_rate, demand_kw, bill_period_end, contract_account
- **Output:** va_step1_base.xlsx (normalized base table)

<a id="fileguide-va-step2-anomalies"></a>

### src/va_step2_anomalies.py

**Purpose:** Data analysis - Step 2

- Loads Step 1 output (va_step1_base.xlsx)
- Adds Year-over-Year (YoY) analysis
- Calculates usage and demand anomalies/spikes
- Computes 12-month history summaries per account
- Identifies accounts exceeding +50% YoY demand threshold
- **Output:** va_step2_anomalies.xlsx

<a id="fileguide-paths"></a>

### src/Configuration_and_paths/paths.py

**Purpose:** Configuration & paths

- Central location for file paths and constants
- Defines:
  - SCHEDULES_XLSX — Schedule parameter file (e.g., Mini_Edit_VEPGA_Schedules_Compact.xlsx)
  - USAGE_INT — Intermediate usage file (va_step1_base.xlsx)
  - RIDERS_OUT — Normalized rider rates
  - EXPORT_DIR — Output directory for results
- Imported by all calculation modules

---

<a id="fileguide-data-files"></a>

---

## Data Files

---


<a id="fileguide-data-raw"></a>

### data/raw/

- City of VA Beach Usage History.xlsb — Original billing data (binary Excel format)

<a id="fileguide-data-interim"></a>

### data/interim/

- Intermediate processing files

<a id="fileguide-data-export"></a>

### data/export/

- Final outputs: usage_savings_output.xlsx, comparisons, summaries

<a id="fileguide-data-schedules"></a>

### data/schedules/

- Mini_Edit_VEPGA_Schedules_Compact.xlsx — Schedule parameters with tabs:
  - Schedule 120, 154, 102, 100, 110 (one sheet per schedule)
  - Columns: Category, Sub-Category, Item, Condition / Tier, Rate / Description, Rate
  - Rows organized by billing type (Non-Demand, Demand) and component (Distribution, ES Supply, Riders)

<a id="fileguide-rider-tables"></a>

### data/rider_tables/ & data/rider_tables_new/

- Rider rate schedule tables with columns: RATE SCHEDULE, AGGREGATE RIDER ADJUSTMENT PER KWH, AGGREGATE RIDER ADJUSTMENT PER KW

---

<a id="fileguide-test-files"></a>

---

## Test Files

---


<a id="fileguide-test-app"></a>

### test/app.py

- Testing/legacy version of billing logic

<a id="fileguide-test-riders-table"></a>

### test/riders_table.py

- Testing/legacy version of rider parsing

---

<a id="fileguide-configuration-files"></a>

---

## Configuration Files

---


- **requirements.txt** — Python package dependencies
- **README.md** — Full project documentation with features and usage
- **FILE_GUIDE.md** (this file) — Project structure and data flow documentation

---

<a id="fileguide-data-flow"></a>

---

## Data Flow

---


```
Raw Data (City VA Beach .xlsb)
    ↓
va_step1_base.py (normalize dates, columns, ensure required fields)
    ↓ [va_step1_base.xlsx]
va_step2_anomalies.py (add YoY, anomalies, 12-month summaries)
    ↓ [va_step2_anomalies.xlsx]
app_new.py (schedule_100/102/110/120/154 functions)
    ├─ Load schedules from SCHEDULES_XLSX
    ├─ Load riders from RIDERS_OUT
    ├─ Extract parameters per billing type (Non-Demand/Demand)
    ├─ Calculate charges per row
    ├─ Determine case type vs. current rate
    ↓
[usage_savings_output.xlsx] — Combined results (all schedules side-by-side)
    ↓
streamlit.py (load output, display & compare)
    ↓
Excel Export (download 12-month comparison)
```

---

<a id="fileguide-key-implementation-notes"></a>

---

## Key Implementation Notes

---


<a id="fileguide-billing-type-determination"></a>

### Billing Type Determination

- **Schedule 102 (VE-102):** Unmetered if any month in last 12m has usage ≤ 49 kWh → uses CUST_CHG_UNMETERED
- **Schedule 100/110 (VE-100/VE-110):** Non-Demand if all months in last 12m have usage < 10,000 kWh → uses flatter ES rates and suppresses kW rider component

<a id="fileguide-es-charge-logic"></a>

### ES Charge Logic

- **Non-Demand:** Flat per-kWh rate applied to all usage (seasonal where applicable)
- **Demand:** Tiered buckets (150 kWh per bucket) across up to 4 tiers, seasonal if defined
- Demand tiers extracted from Excel rows with Item containing 'Tier 1'–'Tier 4' or Condition containing 'First 150 kWh', 'Next 150 kWh', 'Additional'

<a id="fileguide-parameter-extraction"></a>

### Parameter Extraction

- Relies on exact column values: Category, Sub-Category, Item, Condition / Tier
- Format changes in Excel will break lookups → validate parameter sheets before processing
- Missing parameter rows raise ValueError

<a id="fileguide-rider-handling"></a>

### Rider Handling

- Per-kWh riders always apply to usage_kwh
- Per-kW riders apply to demand_kw except for Non-Demand accounts (set to 0)
- Rider rates parsed via _parse_money_series() to handle '$', commas, parentheses negatives, 'N/A'

<a id="fileguide-output-behavior"></a>

### Output Behavior

- Each schedule function returns selected columns only (calculated_amount, savings, case_type, parameters)
- Main loop concatenates results side-by-side into combined DataFrame
- File written after each schedule (overwrites; consider batching if high I/O cost)

---

<a id="fileguide-quick-start"></a>

---

## Quick Start

---


1. Ensure data files are in `data/raw/` and schedule parameters in `data/schedules/`
2. Run: `streamlit run src/streamlit.py`
3. Select account and rate schedule
4. View comparison and export to Excel
