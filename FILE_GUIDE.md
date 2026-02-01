# VA Test Project - File Guide

## 📁 Project Structure Overview
A Streamlit-based electricity tariff billing comparison tool for Virginia Beach (VEPGA rate schedules).

---

## 📄 **Core Files**

### **src/app_new.py**
**Purpose:** Billing engine & core logic
- Loads customer usage history and rider (surcharge) data
- Implements schedule calculation functions (Schedule 100, 102, 110, 120, 154)
- Calculates per-row charges: customer charge, distribution, ES (electricity supply), riders
- Determines billing type: Demand vs. Non-Demand based on 12-month usage rules
- Returns computed charges and savings for each schedule
- **Output:** Combined DataFrame with all schedules' calculations

### **src/streamlit.py**
**Purpose:** Web UI for browsing and comparing billing
- Streamlit app that displays last 12 months of usage data
- Allows user to select account and rate schedule
- Tab 1: Shows account details with historical billing
- Tab 2: Compares current charges vs. selected schedule charges
- Excel export feature: Downloads 12-month comparison
- **Entry point:** `streamlit run src/streamlit.py`

### **src/riders_table_new.py**
**Purpose:** Parse and prepare rider (surcharge) data
- Loads rider rate tables from Excel
- Normalizes columns: schedule code, per-kWh rates, per-kW rates
- **Output:** riders_df used by schedules

### **src/va_step1_base.py**
**Purpose:** Data preparation - Step 1
- Loads raw billing data from City of VA Beach usage history file
- Normalizes dates (handles Excel serial dates, timestamps, strings)
- Cleans and standardizes column names and data types
- **Output:** va_step1_base.xlsx (normalized base table)

### **src/va_step2_anomalies.py**
**Purpose:** Data analysis - Step 2
- Adds Year-over-Year (YoY) analysis to Step 1 output
- Calculates usage and demand anomalies/spikes
- Computes 12-month history summaries per account
- Identifies accounts exceeding +50% YoY demand threshold
- **Output:** va_step2_anomalies.xlsx

### **src/paths.py**
**Purpose:** Configuration & paths
- Central location for file paths and constants
- Defines: `SCHEDULES_XLSX`, `USAGE_INT`, `RIDERS_OUT`, `EXPORT_DIR`, etc.
- Imported by other modules

---

## 📊 **Data Files**

### **data/raw/**
- `City of VA Beach Usage History.xlsb` — Original billing data (binary Excel format)

### **data/interim/**
- Intermediate processing files

### **data/export/**
- Final outputs (Excel comparisons, summaries)

### **data/rider_tables/** & **data/rider_tables_new/**
- Rider rate schedule tables

---

## 🧪 **Test Files**

### **test/app.py**
- Testing/legacy version of billing logic

### **test/riders_table.py**
- Testing/legacy version of rider parsing

---

## 📋 **Configuration Files**

### **requirements.txt**
- Python package dependencies

### **README.md**
- Full project documentation with features and usage

---

## 🔄 **Data Flow**

```
Raw Data (City VA Beach .xlsb)
    ↓
va_step1_base.py (normalize dates, columns)
    ↓ [va_step1_base.xlsx]
va_step2_anomalies.py (add YoY, anomalies)
    ↓ [va_step2_anomalies.xlsx]
app_new.py (calculate schedules)
    ↓
streamlit.py (display & compare)
    ↓
Excel Export (download comparison)
```

---

## 🚀 **Quick Start**
1. Ensure data files are in `data/raw/`
2. Run: `streamlit run src/streamlit.py`
3. Select account and rate schedule
4. View comparison and export to Excel
