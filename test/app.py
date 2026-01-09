import streamlit as st
import pandas as pd
from pathlib import Path

# -------------------------------------------------------------------
# 1. Load data and models once
# -------------------------------------------------------------------

@st.cache_data
def load_bill_data() -> pd.DataFrame:
    # Replace with your real path and loader.
    # Expected columns: contract_account, contract_account, customer, bill_end_date, usage_kwh, demand_kw, ...
    bills_path = Path("data/va_step1_base.xlsx")
    df = pd.read_excel(bills_path)

    # Ensure date column is datetime
    df["bill_end_date"] = pd.to_datetime(df["bill_period_end"])
    return df


@st.cache_data
def load_schedule_list() -> pd.DataFrame:
    # Replace with your real path and loader.
    # Expected columns: rate_code_norm, rate_code_norm (optional)
    schedules_path = Path("data/VEPGA_Schedules_Mini.xlsx")
    df = pd.read_excel(schedules_path)
    return df


# This is a wrapper around your existing calculation logic.
def calculate_schedule_for_account(contract_account: str, rate_code_norm: str) -> pd.DataFrame:
    """
    TODO: Replace this stub with your real schedule calculation function.

    Must return a DataFrame with at least:
    ['bill_end_date', 'rate_code_norm',
     'customer_charge', 'distribution_charge',
     'energy_supply_charge', 'riders_charge', 'total_charge']
    for multiple months of that account and schedule.
    """
    # Placeholder example (fake numbers), DELETE this and plug your real logic.
    # In real code you will look up usage/demand for that contract_account from bill_df
    # and apply the rates from the schedule file.
    bills = bill_df[bill_df["contract_account"] == contract_account].copy()

    # keep last 12 bill_end_date
    bills = bills.sort_values("bill_end_date").tail(12)

    bills["rate_code_norm"] = rate_code_norm
    bills["customer_charge"] = 6.59
    bills["distribution_charge"] = bills["usage_kwh"] * 0.00801
    bills["energy_supply_charge"] = bills["usage_kwh"] * 0.03293
    bills["riders_charge"] = bills["usage_kwh"] * 0.066646
    bills["total_charge"] = (
        bills["customer_charge"]
        + bills["distribution_charge"]
        + bills["energy_supply_charge"]
        + bills["riders_charge"]
    )

    # Keep only the relevant columns for the UI
    return bills[
        [
            "bill_end_date",
            "rate_code_norm",
            "customer_charge",
            "distribution_charge",
            "energy_supply_charge",
            "riders_charge",
            "total_charge",
        ]
    ]


def calculate_for_schedules(contract_account: str, rate_code_norms: list[str]) -> pd.DataFrame:
    """
    Calls your schedule calculation for each selected schedule and concatenates.
    """
    frames = []
    for sid in rate_code_norms:
        df_s = calculate_schedule_for_account(contract_account, sid)
        frames.append(df_s)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Ensure last 12 months overall, in case some schedules have longer history
    result = result.sort_values("bill_end_date").groupby("rate_code_norm").tail(12)

    # Sort final table by date ascending then schedule
    result = result.sort_values(["bill_end_date", "rate_code_norm"])
    return result


# -------------------------------------------------------------------
# 2. Load global data
# -------------------------------------------------------------------

bill_df = load_bill_data()
schedule_df = load_schedule_list()

# Create a label for dropdown: "contract_account - customer"
bill_df["account_label"] = (
    bill_df["contract_account"].astype(str) + " - " + bill_df["customer"].astype(str)
)

# Deduplicate accounts
account_list = (
    bill_df[["contract_account", "account_label"]]
    .drop_duplicates()
    .sort_values("account_label")
    .reset_index(drop=True)
)

# Prepare schedules list
if "rate_code_norm" in schedule_df.columns:
    schedule_df["schedule_label"] = (
        schedule_df["rate_code_norm"].astype(str)
        + " - "
    )
else:
    schedule_df["schedule_label"] = schedule_df["rate_code_norm"].astype(str)

schedule_list = (
    schedule_df[["rate_code_norm", "schedule_label"]]
    .drop_duplicates()
    .sort_values("schedule_label")
    .reset_index(drop=True)
)

# -------------------------------------------------------------------
# 3. UI Layout
# -------------------------------------------------------------------

st.set_page_config(page_title="Tariff Comparison Demo", layout="wide")

st.title("Tariff Schedule Comparison – 12-Month Bill View")

st.markdown(
    "Select an account and one or more schedules. "
    "By default, calculations for **all schedules** will be shown for the last 12 bill periods."
)

# ---- Top controls (account + schedules) ----
col1, col2 = st.columns([2, 3])

with col1:
    selected_account_label = st.selectbox(
        "Account # – Customer Name",
        options=account_list["account_label"].tolist(),
        index=0,
    )

    # Map label back to contract_account
    selected_contract_account = account_list.loc[
        account_list["account_label"] == selected_account_label, "contract_account"
    ].iloc[0]

with col2:
    schedule_options = schedule_list["schedule_label"].tolist()
    all_schedules_label = "All schedules (default)"

    # Add an "All schedules" option visually
    selected_schedule_labels = st.multiselect(
        "Schedules",
        options=[all_schedules_label] + schedule_options,
        default=[all_schedules_label],
        help="Select one or more schedules. If you keep 'All schedules' selected, all available schedules will be used.",
    )

# Determine actual rate_code_norms to use
if all_schedules_label in selected_schedule_labels:
    selected_rate_code_norms = schedule_list["rate_code_norm"].tolist()
else:
    # Map chosen labels back to rate_code_norm
    selected_rate_code_norms = (
        schedule_list[
            schedule_list["schedule_label"].isin(selected_schedule_labels)
        ]["rate_code_norm"]
        .tolist()
    )

st.markdown("---")

# -------------------------------------------------------------------
# 4. Run calculation and show results
# -------------------------------------------------------------------

if st.button("Run calculation"):
    with st.spinner("Calculating charges for selected schedules..."):
        result_df = calculate_for_schedules(selected_contract_account, selected_rate_code_norms)

    if result_df.empty:
        st.warning("No results found for this account / schedule combination.")
    else:
        # Formatting
        result_df_display = result_df.copy()
        result_df_display["bill_end_date"] = result_df_display["bill_end_date"].dt.date

        # Optional: pivot so that each row is a month, and columns per schedule total
        st.subheader("Tabular view – last 12 bill periods")

        st.dataframe(
            result_df_display,
            width='stretch',
        )

        # If you want a pivoted summary:
        with st.expander("Pivoted view (total charge by schedule and month)"):
            pivot_df = result_df_display.pivot_table(
                index="bill_end_date",
                columns="rate_code_norm",
                values="total_charge",
                aggfunc="sum",
            ).sort_index()
            st.dataframe(pivot_df, width='stretch')

        # Optional: export to Excel / CSV
        csv_data = result_df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download detailed results as CSV",
            data=csv_data,
            file_name="schedule_comparison_12_months.csv",
            mime="text/csv",
        )
