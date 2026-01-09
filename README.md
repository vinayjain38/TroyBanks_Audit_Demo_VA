# Tariff Demo – Rate Schedule Comparison Tool

A Streamlit-based web application that calculates and compares electricity billing charges under multiple VEPGA rate schedules (e.g., Schedule 100, 110, 154, etc.).  
The tool processes historical account usage, applies billing rules defined in Excel rate schedules, and provides a 12-month comparison of customer charges, distribution charges, electricity supply (ES) charges, and riders.

## Features
✓ Upload customer usage and rider data
- Accepts billing records with:
    ```
    bill_period_end
    contract_account
    customer
    address_suppl
    usage_kwh
    demand_kw
    charges
    ```
✓ Automatic Schedule Classification
- Determines Non-Demand vs Demand billing based on 12-month history:

    - Non-Demand → all months ≤ 9,999 kWh
    - Demand → any month ≥ 10,000 kWh and demand meter present

✓ Implements Full Billing Rules
- Currently supported:
    - Schedule 100
    - Schedule 102
    - Schedule 110
    - Schedule 120
    - Additional schedules may be added easily.

✓ Rate Schedule Comparison (TAB 2)
- Shows last 12 months of billing activity. Displays:
    - Current rate charges
    - Calculated charges for selected schedule
    - Adds a TOTAL row (bold)
    - Columns formatted, decimals rounded, readable layout

✓ Excel Export
- Download the 12-month comparison with the account number in filename.

## 📂 Project Structure
```
tariff_demo/
│
├── app_new.py                 # Core billing logic (rate schedules)
├── streamlit.py               # Streamlit UI
├── data/
│   ├── Mini_Edit_VEPGA_Schedules_Compact.xlsx   # Official rate schedule tables
│   └── sample_input.xlsx      # Example customer usage file
│
├── .venv/                     # Virtual environment (ignored in Git)
├── README.md
└── requirements.txt
```

## Installation
```
git clone <repo>
cd <repo>
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the App
```
streamlit run streamlit.py
```

## 🧠 How Billing Logic Works

Each rate schedule follows these steps:

1. Determine billing category (Non-Demand vs Demand)

2. Load rates from Excel file:

    - Customer charge
    - Distribution charge
    - Electricity Supply (ES)
    - Tiered or flat rates
    - Riders (per kWh, per kW)

3. Apply season rules (e.g., summer vs base or On-peak vs Off-peak)

4. Calculate final charges per month

5. Return a DataFrame aligned with original usage data


## 🧩 Adding a New Rate Schedule

To add a schedule:

1. Create a new function in app_new.py:

    ``` def schedule_XXX(df, riders_df):```


2. Load relevant parameters from the Excel schedule file.

3. Implement billing rules.

4. Register it:
    ```
    SCHEDULE_FUNCS = {
        "100": schedule_100,
        "110": schedule_110,
        "154": schedule_154,
        ...
    }
    ```

## 📦 Dependencies

Key packages:
```
streamlit
pandas
numpy
xlsxwriter
openpyxl
pyarrow
```




## License
Proprietary unless otherwise specified.
