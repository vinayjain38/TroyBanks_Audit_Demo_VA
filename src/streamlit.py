"""
File: streamlit.py

Overview:  
- Purpose: Streamlit UI to browse an accounts last 12 months of usage and compare billing under different VE schedules.  
- Entry: run with `streamlit run src/streamlit.py`.

Setup / imports:  
- Project root hack: inserts repo root into `sys.path` so `src.*` imports work.  
- Main imports: `streamlit as st`, `pandas as pd`, schedule functions from `src.app_new`, and paths (`USAGE_INT`, `RIDERS_OUT`) from `src.paths`.

Data loading:  
- `load_all()`: calls `load_usage(USAGE_INT)` and `load_riders(RIDERS_OUT)`, ensures `customer_name` exists. Returns `usage_df, riders_df`.

Controls & filtering:  
- Account dropdown: builds `acct_display` = `contract_account + " | " + customer`. Selected `contract_id` filters `usage_df`.  
- Schedule dropdown: lists keys from `SCHEDULE_FUNCS` and sets `schedule_id`.

Tab 1 — Account Details:  
- Cleans `bill_period_end` to datetime, drops rows without dates, sorts and takes last 12 rows, formats dates, and displays a table with core columns (`bill_period_end`, `usage_kwh`, `charges`, etc.).

Tab 2 — Rate Comparison:  
- Runs the selected schedule: `schedule_out = func(df_last12, riders_df)`.  
- Merges base columns (`bill_period_end`, `current_rate`, `usage_kwh`, `demand_kw`, `charges`) with `schedule_out` side-by-side.  
- Adds a totals row via `add_total()` (numeric sums, `bill_period_end="TOTAL"`).  
- Removes any `case_type` columns and reorders to put `bill_period_end` first.  
- Builds a `column_config` to format rider columns (`ve*_rider_charge`) with `RIDER_DECIMALS = 6` using `st.column_config.NumberColumn`.  
- Displays the DataFrame with `st.dataframe(..., column_config=col_cfg)`.

Export:  
- `export_excel()` builds an in-memory Excel via `pd.ExcelWriter(..., engine="xlsxwriter")`. A `st.download_button` lets user download the comparison.

Assumptions & caveats:  
- `src.app_new` schedule functions must return per-row columns the UI expects (e.g., `ve{sid}_rider_charge`, `ve{sid}_es_charge`, `ve{sid}_cust_charge`).  
- Date parsing drops invalid rows — accounts without valid bill dates will show a warning.  
- `xlsxwriter` must be installed for Excel export.  
- Large data files should typically remain out of git or be managed with Git LFS.

"""

# import streamlit as st
# import pandas as pd
# import os

# # Import your schedule functions
# from app_new import (
#     load_usage,
#     load_riders,
#     schedule_100,
#     schedule_102,
#     schedule_110,
#     schedule_120,
#     schedule_154,
#     SCHEDULE_FUNCS,
#     USAGE_INT,
#     RIDERS_OUT
# )

# st.set_page_config(
#     page_title="Tariff Rate Comparison",
#     layout="wide",            # FULL WIDTH PAGE
# )

# # ---------------------------------------------------
# # Load Data Once (Cached)
# # ---------------------------------------------------
# @st.cache_data
# def load_all_data():
#     usage_df = load_usage(USAGE_INT)
#     riders_df = load_riders(RIDERS_OUT)
#     return usage_df, riders_df


# usage_df, riders_df = load_all_data()

# # ---------------------------------------------------
# # Page Title
# # ---------------------------------------------------
# st.title("Tariff Schedule Comparison – 12 Month View")
# col1, col2 = st.columns([2, 1])

# st.write("Select an Account and Schedule Rate to view details & comparisons.")


# # ---------------------------------------------------
# # 1. ACCOUNT DROPDOWN
# # ---------------------------------------------------
# usage_df["acct_display"] = (
#     usage_df["contract_account"].astype(str)
#     + " | "
#     + usage_df["customer"].astype(str)
# )

# with col1:
#     acct_display = st.selectbox("Account – Customer", sorted(usage_df["acct_display"].unique()))
#     contract_id = acct_display.split(" | ")[0]

# # Filter base data for account
# df_acct = usage_df[usage_df["contract_account"] == contract_id].copy()


# # ---------------------------------------------------
# # 2. SCHEDULE DROPDOWN
# # ---------------------------------------------------
# with col2:
#     schedule_list = sorted(list(SCHEDULE_FUNCS.keys()))
#     schedule_selected = st.selectbox(
#         "Select Rate Schedule:",
#         options=schedule_list,
#         index=0
#     )

# st.divider()

# # ---------------------------------------------------
# # 3. BUILD LAST 12 MONTHS VIEW
# # ---------------------------------------------------
# def get_last_12_months(df):
#     df = df.sort_values("bill_period_end")
#     return df.tail(12).copy()


# df_last12 = get_last_12_months(df_acct)

# # ---------------------------------------------------
# # 4. RUN ALL SCHEDULE CALCULATIONS FOR THE RATE COMPARISON TAB
# # ---------------------------------------------------
# comparison_df = df_last12.copy()

# for sid, func in SCHEDULE_FUNCS.items():
#     try:
#         out = func(df_last12, riders_df)
#         # out is a dataframe with columns specific to schedule
#         # Prefix schedule ID to avoid duplicates
#         out = out.add_prefix(f"ve{sid}_")
#         comparison_df = pd.concat([comparison_df, out], axis=1)
#     except Exception as e:
#         st.warning(f"Schedule {sid} skipped due to error: {e}")

# # ---------------------------------------------------
# # 5. Add TOTAL ROW at bottom (bold)
# # ---------------------------------------------------
# def add_totals_row(df):
#     totals = {}
#     for col in df.columns:
#         if pd.api.types.is_numeric_dtype(df[col]):
#             totals[col] = df[col].sum()
#         else:
#             totals[col] = ""
#     df_totals = pd.DataFrame([totals], index=["TOTAL"])
#     return pd.concat([df, df_totals])


# comparison_df_totals = add_totals_row(comparison_df)

# # ---------------------------------------------------
# # TABS LAYOUT
# # ---------------------------------------------------
# tab1, tab2 = st.tabs(["Account Details", "Rate Comparison"])

# # ---------------------------------------------------
# # TAB 1 – ACCOUNT DETAILS
# # ---------------------------------------------------
# with tab1:
#     st.subheader("Customer Billing History (Last 12 Months)")
#     cols_to_show = [
#         "contract_account",
#         "customer",
#         "current_rate",
#         "address_suppl",
#         "bill_period_end",
#         "usage_kwh",
#         "demand_kw",
#         "charges"
#     ]

#     df_acc_details = df_acct[cols_to_show].copy()
#     st.dataframe(df_acc_details, width='stretch')

# # ---------------------------------------------------
# # TAB 2 – RATE COMPARISON
# # ---------------------------------------------------
# with tab2:
#     st.subheader("Rate Comparison Across Schedules")

#     # Move TOTAL row at bottom and highlight it
#     st.dataframe(
#         comparison_df_totals.style.apply(
#             lambda x: ["font-weight: bold" if x.name == "TOTAL" else "" for _ in x],
#             axis=1
#         ),
#         width='stretch'
#     )

#     st.caption("Bottom row shows totals for numeric columns.")
from pathlib import Path
import sys

# Ensure project root is on PYTHONPATH so `import src...` works when running:
# streamlit run src/streamlit.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import streamlit as st
import pandas as pd
import re

from src.app_new import (
    load_usage, load_riders,
    schedule_100, schedule_102, schedule_110,
    schedule_120, schedule_154,
    SCHEDULE_FUNCS)
#    USAGE_PATH, RIDERS_PATH
from src.paths import USAGE_INT, RIDERS_OUT


# ---------------------------------------------------
# Streamlit page settings
# ---------------------------------------------------
st.set_page_config(
    page_title="Tariff Rate Comparison",
    layout="wide",            # FULL WIDTH PAGE
)

st.markdown("""
<style>
/* Reduce top padding */
.block-container {
    padding-top: 1rem;
}

/* Reduce space above title */
h1 {
    margin-top: -1.5rem;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------
# Load Data
# ---------------------------------------------------
@st.cache_data
def load_all():
    usage = load_usage(USAGE_INT)
    riders = load_riders(RIDERS_OUT)

    # Normalize missing fields
    if "customer_name" not in usage.columns:
        if "customer" in usage.columns:
            usage["customer_name"] = usage["customer"]
        else:
            usage["customer_name"] = ""

    return usage, riders

usage_df, riders_df = load_all()

# ---------------------------------------------------
# FILTER SECTION – Side-by-side layout
# ---------------------------------------------------
st.title("Tariff Schedule Comparison – 12 Month View")

col1, col2 = st.columns([2, 1])

# -------- ACCOUNT DROPDOWN --------

# Normalize account number
usage_df["contract_account"] = usage_df["contract_account"].astype(str).str.strip()

usage_df["acct_display"] = (
    usage_df["contract_account"].astype(str)
    + " | "
    + usage_df["customer"].astype(str)
)

with col1:
    acct_display = st.selectbox("Account – Customer", sorted(usage_df["acct_display"].unique()))
    contract_id = acct_display.split(" | ")[0]

# Filter base data for account
# df_acct = usage_df[usage_df["contract_account"] == contract_id].copy()
df_acct = usage_df[usage_df["contract_account"].astype(str).str.strip() == contract_id.strip()].copy()


# -------- SCHEDULE DROPDOWN --------
with col2:
    schedule_id = st.selectbox("Schedule", sorted(SCHEDULE_FUNCS.keys()))

# st.divider()

# ---------------------------------------------------
# ACCOUNT DETAILS (TAB 1)
# ---------------------------------------------------
tab1, tab2 = st.tabs(["Account Details", "Rate Comparison"])

with tab1:
    st.subheader("Customer Billing History (Last 12 Months)")

    # --- Fix: Clean invalid dates safely ---
    df_acct["bill_period_end"] = pd.to_datetime(
        df_acct["bill_period_end"], 
        errors="coerce"         # converts invalid values (like ...) → NaT
    )

    # Drop rows with no dates
    df_acct = df_acct.dropna(subset=["bill_period_end"])
        
    # Ensure we only show last 12 rows sorted by date
    df_acct_sorted = df_acct.sort_values("bill_period_end")
    df_last12 = df_acct_sorted.tail(12).copy()

    df_last12["bill_period_end"] = pd.to_datetime(
    df_last12["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")

    df_last12["bill_period_end"] = df_last12["bill_period_end"].fillna("")

    # If still empty, show friendly error
    if df_last12.empty:
        st.warning("No valid billing dates found for this account.")
        st.write(df_acct.head())
        st.stop()

    # Format dates
    df_last12 = df_last12.copy()
    df_last12.loc[:, "bill_period_end"] = pd.to_datetime(df_last12["bill_period_end"]).dt.strftime("%Y-%m-%d")


    # Select required columns
    desired_cols = [
        "bill_period_end",
        "contract_account",
        "customer",
        "current_rate",
        "address_suppl",
        "usage_kwh",
        "demand_kw",
        "charges"
    ]

    # Ensure only existing columns are taken
    final_cols = [c for c in desired_cols if c in df_last12.columns]
    display_df = df_last12[final_cols].reset_index(drop=True)

    st.dataframe(
        display_df,
        width='stretch',
        hide_index=True,
        height=500  # Adjust height based on your screen
    )

# ---------------------------------------------------
# RATE COMPARISON (TAB 2)
# ---------------------------------------------------
# with tab2:
#     st.subheader("Rate Schedule Comparison – Last 12 Months")

#     # Last 12 months
#     df_acct_sorted = df_acct.sort_values("bill_period_end")
#     df_last12 = df_acct_sorted.tail(12)
#     df_last12 = df_last12.copy()
#     df_last12.loc[:, "bill_period_end"] = pd.to_datetime(df_last12["bill_period_end"]).dt.strftime("%Y-%m-%d")


#     if df_last12.empty:
#         st.warning("This account does not have 12 months of billing data.")
#         st.stop()

#     # Run selected schedule
#     func = SCHEDULE_FUNCS[schedule_id]
#     schedule_out = func(df_last12, riders_df)
#     # schedule_out = schedule_out.add_prefix(f"ve{schedule_id}_")

#     # Build final table
#     base_cols = ["bill_period_end","current_rate", "usage_kwh", "demand_kw", "charges"]
#     merged = pd.concat([df_last12[base_cols].reset_index(drop=True),
#                         schedule_out.reset_index(drop=True)], axis=1)
#     merged = merged.loc[:, ~merged.columns.duplicated()]
#     merged = merged.reset_index(drop=True)

#     # # Add Totals Row
#     # def add_total(df):
#     #     totals = {}
#     #     for col in df.columns:
#     #         if pd.api.types.is_numeric_dtype(df[col]):
#     #             totals[col] = df[col].sum()
#     #         else:
#     #             totals[col] = ""
#     #     return pd.concat([df, pd.DataFrame([totals], index=["TOTAL"])])

#     def add_total(df):
#         # Sum only numeric columns
#         numeric_totals = df.select_dtypes(include=['number']).sum()

#         # Build a totals row that aligns with ALL columns
#         totals_row = {col: numeric_totals.get(col, "") for col in df.columns}

#         # Create a DataFrame for the totals row
#         total_df = pd.DataFrame([totals_row], index=["TOTAL"])

#         # Return concatenated output with safe reset_index
#         df_out = pd.concat([df, total_df], axis=0)

#         return df_out
    
#     def add_total(df):
#         numeric_cols = df.select_dtypes(include=["number"]).columns

#         totals = df[numeric_cols].sum()

#         # Create an empty row with correct schema
#         empty_row = {col: None for col in df.columns}

#         # Fill numeric totals
#         for col in numeric_cols:
#             empty_row[col] = totals[col]

#         # Identify row as TOTAL
#         empty_row["bill_period_end"] = "TOTAL"

#         # Append safely
#         df_total = pd.concat([df, pd.DataFrame([empty_row])], ignore_index=True)

#         return df_total

#     merged_totals = add_total(merged)
    
#     # Remove any ve*_case_type columns
#     merged_totals = merged_totals.loc[
#         :, ~merged_totals.columns.str.contains("case_type", case=False)]

#     merged_totals["bill_period_end_fmt"] = pd.to_datetime(merged_totals["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    
#     mask = merged_totals["bill_period_end_fmt"].isna()
#     merged_totals.loc[mask, "bill_period_end_fmt"] = merged_totals.loc[mask, "bill_period_end"]

#     merged_totals["bill_period_end"] = merged_totals["bill_period_end"].astype(str)

#     # Replace column
#     merged_totals = merged_totals.drop(columns=["bill_period_end"])
#     merged_totals = merged_totals.rename(columns={"bill_period_end_fmt": "bill_period_end"})

#     # --- Reduce decimal places in Tab 2 (all numeric columns) ---
#     numeric_cols = merged_totals.select_dtypes(include=["float", "int"]).columns

#     # merged_totals[numeric_cols] = merged_totals[numeric_cols].apply(
#     #     lambda col: col.round(3) 
#     # )
#     merged_totals[numeric_cols] = merged_totals[numeric_cols].round(2)


#     # Reduce decimals for numeric columns
#     # numeric_cols = merged_totals.select_dtypes(include=["number"]).columns
#     # merged_totals[numeric_cols] = merged_totals[numeric_cols].round(2)


with tab2:
    st.subheader("Rate Schedule Comparison – Last 12 Months")

    # ---- Select last 12 months ----
    df_acct_sorted = df_acct.sort_values("bill_period_end")
    df_last12 = df_acct_sorted.tail(12).copy()

    if df_last12.empty:
        st.warning("This account does not have 12 months of billing data.")
        st.stop()

    df_last12["bill_period_end"] = pd.to_datetime(
    df_last12["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")

    df_last12["bill_period_end"] = df_last12["bill_period_end"].fillna("")


    # ---- Run selected schedule ----
    func = SCHEDULE_FUNCS[schedule_id]
    schedule_out = func(df_last12, riders_df)

    # ---- Base columns ----
    base_cols = ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"]

    merged = pd.concat(
        [df_last12[base_cols].reset_index(drop=True),
         schedule_out.reset_index(drop=True)],
        axis=1
    )

    merged = merged.loc[:, ~merged.columns.duplicated()].reset_index(drop=True)

    # ---- Add total row ----
    def add_total(df):
        numeric_cols = df.select_dtypes(include=["number"]).columns
        totals = df[numeric_cols].sum()

        row = {col: None for col in df.columns}
        for col in numeric_cols:
            row[col] = totals[col]

        row["bill_period_end"] = "TOTAL"
        return pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    merged_totals = add_total(merged)

    # ---- Remove case_type columns ----
    merged_totals = merged_totals.loc[
        :, ~merged_totals.columns.str.contains("case_type", case=False)
    ]

    # ---- Round all numeric columns to 2 decimals ----
    num_cols = merged_totals.select_dtypes(include=["float", "int"]).columns
    merged_totals[num_cols] = merged_totals[num_cols]  #.round(2)

    # ---- Reorder: make bill_period_end the first column ----
    cols = merged_totals.columns.tolist()
    cols.remove("bill_period_end")
    cols = ["bill_period_end"] + cols
    merged_totals = merged_totals[cols]

    # Choose precision
    RIDER_DECIMALS = 6

    # Identify rider columns (adjust pattern if needed)
    rider_cols = [c for c in merged_totals.columns if re.match(r"^ve\d+_rider_charge$", c)]

    col_cfg = {}
    for c in rider_cols:
        col_cfg[c] = st.column_config.NumberColumn(
            c,
            format=f"$%.{RIDER_DECIMALS}f"
        )

    # ---- Display Rates on top----

    # # ---- Selected-schedule parameters (show top/representative values) ----
    # try:
    #     params_df = schedule_out.reset_index(drop=True)

    #     def first_non_null(df, candidates):
    #         for c in candidates:
    #             if c in df.columns:
    #                 s = df[c].dropna()
    #                 if not s.empty:
    #                     return s.iloc[0]
    #         return None

    #     prefix = f"ve{schedule_id}_"
    #     cust_val = first_non_null(params_df, [prefix + "cust_charge"])
    #     dist_val = first_non_null(params_df, [prefix + "dist_rate", prefix + "dist_charge"])

    #     # ES: schedule 120 exposes on/off peak; others may expose es_rate or es_charge
    #     if schedule_id == '120':
    #         es_on = first_non_null(params_df, [prefix + "es_on_peak"])
    #         es_off = first_non_null(params_df, [prefix + "es_off_peak"])
    #         es_display = None
    #         if es_on is not None and es_off is not None:
    #             es_display = f"On: ${float(es_on):.4f} / Off: ${float(es_off):.4f}"
    #         else:
    #             es_display = es_on or es_off
    #     else:
    #         es_raw = first_non_null(params_df, [prefix + "es_rate", prefix + "es_charge", prefix + "es_blend"])
    #         es_display = es_raw

    #     rider_val = first_non_null(params_df, [prefix + "rider_kwh", prefix + "rider_charge", prefix + "rider"])

    #     # Format values for display
    #     def fmt_money(v, prec=2):
    #         try:
    #             return f"${float(v):,.{prec}f}"
    #         except Exception:
    #             return "-"

    #     def fmt_rate(v):
    #         try:
    #             return f"${float(v):.4f} /kWh"
    #         except Exception:
    #             return "-"

    #     c1, c2, c3, c4 = st.columns(4)
    #     with c1:
    #         c1.metric("Customer Charge", fmt_money(cust_val) if cust_val is not None else "-")
    #     with c2:
    #         c2.metric("Distribution Rate", fmt_rate(dist_val) if dist_val is not None else "-")
    #     with c3:
    #         c3.metric("Supply Charge", fmt_rate(es_display) if es_display is not None else "-")
    #     with c4:
    #         c4.metric("Rider $", fmt_money(rider_val, prec=4) if rider_val is not None else "-")
    # except Exception:
    #     # non-fatal: if params can't be shown, continue to show table
    #     pass

    st.dataframe(merged_totals, width='stretch', height=500, hide_index=True, column_config=col_cfg)


    # Excel download
    def export_excel(df):
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Schedule_Output")
        return buffer.getvalue()

    st.download_button(
        label="Download Excel",
        data=export_excel(merged_totals),
        file_name=f"{contract_id}_VE{schedule_id}_comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# if __name__ == "__main__":
#     main()