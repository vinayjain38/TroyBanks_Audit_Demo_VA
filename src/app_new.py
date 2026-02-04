# Overview:

# File: app_new.py — billing engine that reads base usage + schedule/rider parameter sheets, computes per-row charges for multiple VE schedules, and writes a combined output.
# Key helpers:

# load_usage(): loads the base usage Excel, ensures usage_kwh, charges, current_rate, demand_kw exist.
# load_riders(): loads the riders Excel and normalizes columns: schedule_code, numeric rider_total_per_kwh and rider_total_per_kw.
# Schedule functions (core logic):
# Each schedule function (120, 154, 102, 100, 110) follows the same pattern:

# Read sheet name from the schedules workbook (SCHEDULES_XLSX).
# Extract customer charge(s), distribution rate(s), ES supply rates, and riders (per-kWh and per-kW) from parameter rows.
# Determine billing type per account (Non‑Demand vs Demand) by checking last-12-months usage rules (accounts with all monthly usage < 10k → Non-Demand; other schedules use variations like <=49 kWh to pick unmetered). This sets 'is_nondemand'.

# Compute ES charge:
# For Non‑Demand: apply a flat ES rate (seasonal where applicable).
# For Demand: apply tiered ES buckets (150‑kWh buckets, up to 4 tiers) seasonally where defined.
# Each schedule returns an ES charge column (e.g., ve110_es_charge, ve100_es_charge) computed per-row.

# Compute riders and other pieces:
# Rider charge = usage_kwh * rider_kwh + demand_kw * rider_kw (kW part suppressed for Non‑Demand where required).

# Distribution charge = dist_rate * usage_kwh (per-row).

# Customer charge applied per-row (metered vs unmetered or demand/non-demand).

# Aggregate total: *_calculated_amount = cust + dist + es + rider; *_savings = charges - calculated_amount; *_case_type indicates whether the current rate equals that schedule.

# Return shape:
# Each schedule returns a DataFrame with the calculated columns for that schedule (calculated amount, savings, case_type) plus parameter columns (customer charge, dist rate, ES rate/charge where applicable, and rider values). These are concatenated into the combined output in main().

# Registration & main loop:
# SCHEDULE_FUNCS maps schedule ids ('120','154','102','100','110') → functions.
# main() loads usage and riders once, runs each schedule in a loop, concatenates results side-by-side into combined, and writes OUTPUT_PATH Excel after each schedule run (timestamping disabled; file overwritten).

# Implementation notes & caveats:
# Parameter extraction relies on specific column values (Category, Sub-Category, Item, Condition / Tier); format changes in the Excel will break lookups.
# ES tier handling uses fixed 150 kWh buckets for demand schedules — logic assumes tier rows exist and raises if missing.
# Some schedules compute an implied per-kWh ES rate by dividing ES charge by usage (watch for zero usage rows). -- Remove logic
# Rider values are parsed as numeric per-kWh/per-kW via _parse_money_series in load_riders.
# Paths and constants are imported from src.paths (e.g., SCHEDULES_XLSX, USAGE_INT, RIDERS_OUT, EXPORT_DIR) — ensure those are set correctly.
# Writing OUTPUT_PATH after each schedule overwrites the file; consider writing once at the end if you want a single final file.


#!/usr/bin/env python3
import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np
from src.paths import RIDERS_OUT, SCHEDULES_XLSX, EXPORT_DIR, RIDERS_OUT, USAGE_INT

# ==== CONFIGURATION ====
# This is va_step1_base usage file
USAGE_PATH = USAGE_INT

# Directory containing riders files
RIDERS_PATH = RIDERS_OUT

# Use a timestamped filename to avoid PermissionError when a previous file is open in Excel.
# TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_PATH = os.path.join(EXPORT_DIR, f"usage_savings_output.xlsx")

schedule_path = SCHEDULES_XLSX

# Map of schedule codes to their processing functions
SCHEDULE_FUNCS = {}

# ==== HELPERS ====
def load_usage(path: str) -> pd.DataFrame:
    """Load your base usage DataFrame and normalize it."""
    df = pd.read_excel(path)
    df["usage_kwh"] = df["usage_kwh"]  # ensure exists
    df["charges"]    = df["charges"]    # ensure exists
    df["current_rate"] = df["current_rate"]  # ensure exists
    df['demand_kw'] = df['demand_kw'] # ensure exists
    return df

def _parse_money_series(s: pd.Series) -> pd.Series:
    """
    Converts '$0.014945', ' $1,234.50 ', '($0.25)', '', 'N/A' to floats.
    """
    s = s.astype(str).str.strip()

    # common non-values
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "N/A": np.nan, "NA": np.nan})

    # parentheses negatives: (0.25) -> -0.25, ($0.25) -> -$0.25
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)

    # remove $ and commas
    s = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)

    return pd.to_numeric(s, errors="coerce")

def load_riders(path: str) -> pd.DataFrame:
    """Load riders file and normalize columns used by schedule functions.

    - Uses column 'RATE SCHEDULE' for schedule codes when present.
    - Uses 'AGGREGATE RIDER ADJUSTMENT PER KWH' for rider amounts when present.
    - Falls back to reasonable defaults when names differ.
    """
    df = pd.read_excel(path)

    # Normalize column name lookup (lowercase, stripped)
    # lookup = {c.lower().strip(): c for c in df.columns}

    # schedule code column
    # sched_col = lookup.get('rate schedule') or df.columns[0]
    df['schedule_code'] = df['RATE SCHEDULE'].astype(str)

    df['rider_total_per_kwh'] = _parse_money_series(df['AGGREGATE RIDER ADJUSTMENT PER KWH']).fillna(0.0)
    df['rider_total_per_kw']  = _parse_money_series(df['AGGREGATE RIDER ADJUSTMENT PER KW']).fillna(0.0)


    return df

# ==== SCHEDULE 120 ====
def schedule_120(usage_df: pd.DataFrame, riders_df: pd.DataFrame) -> pd.DataFrame:
    # 1. load riders (normalized)
    # riders = load_riders(RIDERS_PATH)
    # riders["schedule_code_norm"] = (
    #     riders["schedule_code"].astype(str).str.upper().str.strip()
    # )
    
    r120 = riders_df[riders_df["schedule_code"].str.contains("SCHEDULE 120")]
    if r120.empty:
        raise ValueError("No row for SCHEDULE 120 in riders file.")
    rate_rider_kwh = float(r120["rider_total_per_kwh"].iloc[0] or 0.0)
    rate_rider_kw = float(r120["rider_total_per_kw"].iloc[0] or 0.0)

    # 2. parameters
    # CUST_CHG = 6.59
    # DIST_RATE = 1.335 / 100.0
    # es_blend = (0.40 * 4.289 + 0.60 * 2.673) / 100.0
    # total_rate = DIST_RATE + es_blend + rate_rider_kwh 
    
    schedule_120 = pd.read_excel(SCHEDULES_XLSX, sheet_name="Schedule 120")
    
    # extract customer charge
    cust_row = schedule_120[
        (schedule_120['Category'] == 'Non-Demand Billing') &
        (schedule_120['Sub-Category'] == 'Distribution') &
        (schedule_120['Item'] == 'Basic Customer Charge')
    ]
    if cust_row.empty:
        raise ValueError("Parameter Basic Customer Charge not found for Schedule 120")
    CUST_CHG = float(cust_row['Rate'].iloc[0])
    
    # extract distribution rate
    dist_row = schedule_120[
        (schedule_120['Category'] == 'Non-Demand Billing') &
        (schedule_120['Sub-Category'] == 'Distribution') &
        (schedule_120['Item'] == 'Energy Charge')
    ]
    if dist_row.empty:
        raise ValueError("Parameter Energy Charge not found for Schedule 120")
    DIST_RATE = float(dist_row['Rate'].iloc[0]) / 100.0 # cents to $
    
    # extract ES supply on-peak rate
    es_onpeak_row = schedule_120[
        (schedule_120['Category'] == 'Non-Demand Billing') &
        (schedule_120['Sub-Category'] == 'ES Supply') &
        (schedule_120['Item'] == 'On-peak')
    ]
    if es_onpeak_row.empty:
        raise ValueError("Parameter ES Supply On-peak not found for Schedule 120")
    ES_ON_PEAK = float(es_onpeak_row['Rate'].iloc[0]) / 100.0

    # extract ES supply off-peak rate
    es_offpeak_row = schedule_120[
        (schedule_120['Category'] == 'Non-Demand Billing') &
        (schedule_120['Sub-Category'] == 'ES Supply') &
        (schedule_120['Item'] == 'Off-peak')
    ]
    if es_offpeak_row.empty:
        raise ValueError("Parameter ES Supply Off-peak not found for Schedule 120")
    ES_OFF_PEAK = float(es_offpeak_row['Rate'].iloc[0]) / 100.0

    ES_BLEND = (0.40 * ES_ON_PEAK + 0.60 * ES_OFF_PEAK)
    total_rate = DIST_RATE + ES_BLEND + rate_rider_kwh

    # 3. apply to base
    df = usage_df.copy()
    # df["ve120_usage_charge"] = df["usage_kwh"] * total_rate
    # df["ve120_demand_charge"] = df.get("demand_kw", 0.0) * rate_rider_kw   # VE-120 may not have demand charge.
    df['ve120_cust_charge'] = CUST_CHG
    df['ve120_dist_rate'] = DIST_RATE
    df['ve120_es_on_peak'] = ES_ON_PEAK
    df['ve120_es_off_peak'] = ES_OFF_PEAK
    df['ve120_es_blend'] = ES_BLEND
    df['ve120_rider_charge'] = rate_rider_kwh

    df["ve120_calculated_amount"] = CUST_CHG + total_rate * df["usage_kwh"] 
    df["ve120_savings"] = df["charges"] - df["ve120_calculated_amount"]
    df["ve120_case_type"] = df["current_rate"].apply(
        lambda x: 'Same Schedule as Current' if x == "VE-120" else 'New Rate Schedule'
    )

    # 4. clean up
    drop = [
        "ve120_usage_charge",
        "ve120_demand_charge"
    ]
    
    # df.to_excel(os.path.join(BASE_DIR, 've120_output.xlsx'), index=False)

    # return df.drop(columns=[c for c in drop if c in df.columns])
    return df[["ve120_calculated_amount", "ve120_savings", "ve120_case_type",
               "ve120_cust_charge", "ve120_dist_rate", "ve120_es_on_peak",
               "ve120_es_off_peak", "ve120_rider_charge"]]

# ==== SCHEDULE 154 ====
def schedule_154(usage_df: pd.DataFrame, riders_df: pd.DataFrame) -> pd.DataFrame:
    
    # 1. load riders (normalized)
    # riders = load_riders(RIDERS_PATH)
    r154 = riders_df[riders_df["schedule_code"].str.contains("SCHEDULE 154")]
    if r154.empty:
        raise ValueError("No row for SCHEDULE 154 in riders file.")
    rate_rider_kwh = float(r154["rider_total_per_kwh"].iloc[0] or 0.0)
    rate_rider_kw = float(r154["rider_total_per_kw"].iloc[0] or 0.0)

    # 2. parameters
    # DIST_RATE = 2.673 / 100.0
    # ES_RATE   = 0.761 / 100.0

    # schedule_154 = pd.read_excel(schedule_path := os.path.join(BASE_DIR, "data", "Mini_Edit_VEPGA_Schedules_Compact.xlsx"),
                                # sheet_name="Schedule 154")
    schedule_154 = pd.read_excel(SCHEDULES_XLSX, sheet_name="Schedule 154")

    custrow_metered = schedule_154[
        (schedule_154['Category'] == 'Non-Demand Billing') &
        (schedule_154['Sub-Category'] == 'Distribution') &
        (schedule_154['Item'] == 'Basic Customer Charge') &
        (schedule_154['Condition / Tier'] == 'Metered')
    ]    
    if custrow_metered.empty:
        raise ValueError("Basic Customer Charge not found for Schedule 154")
    CUST_CHG = float(custrow_metered['Rate'].iloc[0])

    # custrow_unmetered   # Might be     needed for VE-154
    
    distrow = schedule_154[
        (schedule_154['Category'] == 'Non-Demand Billing') &
        (schedule_154['Sub-Category'] == 'Distribution') &
        (schedule_154['Item'] == 'Energy Charge')
    ]
    if distrow.empty:
        raise ValueError("Distribution Energy Charge not found for Schedule 154")
    DIST_RATE = float(distrow['Rate'].iloc[0]) / 100.0  # cents to $
    
    es_row = schedule_154[
        (schedule_154['Category'] == 'Non-Demand Billing') &
        (schedule_154['Sub-Category'] == 'ES Supply') &
        (schedule_154['Item'] == 'Energy Charge')
    ]
    if es_row.empty:
        raise ValueError("ES Supply Energy Charge not found for Schedule 154")
    ES_RATE = float(es_row['Rate'].iloc[0]) / 100.0  # cents to $
    
    total_rate = DIST_RATE + ES_RATE + rate_rider_kwh

    # 3. apply to base
    df = usage_df.copy()
    # Display pulled rates
    df['ve154_cust_charge'] = CUST_CHG
    df['ve154_dist_rate'] = DIST_RATE
    df['ve154_es_rate'] = ES_RATE
    df['ve154_rider_charge'] = rate_rider_kwh
    # df["ve154_usage_charge"] = df["usage_kwh"] * total_rate
    # df["ve154_demand_charge"] = df["demand_kw"] * rate_rider_kw     # VE-154 may not have demand charge.

    df["ve154_calculated_amount"] = CUST_CHG + df["usage_kwh"] * total_rate
    df["ve154_savings"] = df["charges"] - df["ve154_calculated_amount"]
    df["ve154_case_type"] = df["current_rate"].apply(
        lambda x: 'Same Schedule as Current' if x == "VE-154" else 'New Rate Schedule'
    )

    # 4. clean up
    drop = [ "ve154_usage_charge",
            "ve154_demand_charge"
    ]
    
    return df[["ve154_calculated_amount", "ve154_savings", "ve154_case_type",
               "ve154_cust_charge", "ve154_dist_rate", "ve154_es_rate", "ve154_rider_charge"]]

def schedule_102(usage_df: pd.DataFrame, riders_df: str = None) -> pd.DataFrame:
    # load latest riders file
    r102 = riders_df[riders_df["schedule_code"].str.contains("SCHEDULE 102")]
    if r102.empty:
        raise ValueError("No row for SCHEDULE 102 in riders file.")
    rate_rider_kwh = float(r102["rider_total_per_kwh"].iloc[0] or 0.0)
    rate_rider_kw = float(r102["rider_total_per_kw"].iloc[0] or 0.0)

    # compute bill
    # CUST_CHG = 6.59
    # DIST_RATE = 0.00801
    # ES_RATE = 0.03293

    schedule_102 = pd.read_excel(SCHEDULES_XLSX, sheet_name="Schedule 102")

    custrow_metered = schedule_102[
        (schedule_102['Category'] == 'Non-Demand Billing') &
        (schedule_102['Sub-Category'] == 'Distribution') &
        (schedule_102['Item'] == 'Basic Customer Charge') &
        (schedule_102['Condition / Tier'] == 'Metered')
    ]    
    if custrow_metered.empty:
        raise ValueError("Basic Customer Charge not found for Schedule 102")
    CUST_CHG_METERED = float(custrow_metered['Rate'].iloc[0])
    
    custrow_unmetered = schedule_102[
        (schedule_102['Category'] == 'Non-Demand Billing') &
        (schedule_102['Sub-Category'] == 'Distribution') &
        (schedule_102['Item'] == 'Basic Customer Charge') &
        (schedule_102['Condition / Tier'] == 'Unmetered')
    ]
    if custrow_unmetered.empty:
        raise ValueError("Basic Customer Charge (Unmetered) not found for Schedule 102")
    CUST_CHG_UNMETERED = float(custrow_unmetered['Rate'].iloc[0])

    distrow = schedule_102[
        (schedule_102['Category'] == 'Non-Demand Billing') &
        (schedule_102['Sub-Category'] == 'Distribution') &
        (schedule_102['Item'] == 'Energy Charge')
    ]
    if distrow.empty:
        raise ValueError("Distribution Energy Charge not found for Schedule 102")
    DIST_RATE = float(distrow['Rate'].iloc[0]) / 100.0  # cents to $

    es_row = schedule_102[
        (schedule_102['Category'] == 'Non-Demand Billing') &
        (schedule_102['Sub-Category'] == 'ES Supply') &
        (schedule_102['Item'] == 'Energy Charge')
    ]
    if es_row.empty:
        raise ValueError("ES Supply Energy Charge not found for Schedule 102")
    ES_RATE = float(es_row['Rate'].iloc[0]) / 100.0  # cents to $

    total = DIST_RATE + ES_RATE + rate_rider_kwh

    # Determine if the contract_account is unmetered (any usage_kwh <=49
    # in the most recent 12 months for that account).
    
    u = usage_df.copy()
    # ensure bill_period_end is datetime if present
    if 'bill_period_end' in u.columns:
        u['bill_period_end'] = pd.to_datetime(u['bill_period_end'], errors='coerce')

    # compute latest bill date per account
    if 'bill_period_end' in u.columns and u['bill_period_end'].notna().any():
        max_dates = u.groupby('contract_account', dropna=False)['bill_period_end'].max().rename('max_bill').reset_index()
        u = u.merge(max_dates, on='contract_account', how='left')
        u['in_last_12m'] = u['bill_period_end'] >= (u['max_bill'] - pd.Timedelta(days=365))
    else:
        # fallback: if no bill_period_end, consider the last 12 rows per account
        u['_row_order'] = range(len(u))
        u['in_last_12m'] = False
        for acct, grp in u.groupby('contract_account'):
            last12 = grp.sort_values('_row_order').tail(12).index
            u.loc[last12, 'in_last_12m'] = True

    # per-account flag: any usage <=49 within last 12 months window
    flag = u[u['in_last_12m']].groupby('contract_account')['usage_kwh'].apply(lambda s: (s <= 49).any()).rename('any_le_49').reset_index()

    # map to customer charge choice
    flag_map = {row['contract_account']: row['any_le_49'] for _, row in flag.iterrows()}

    df = usage_df.copy()
    # choose cust charge per account
    df['ve102_cust_charge'] = df['contract_account'].map(lambda a: CUST_CHG_UNMETERED if flag_map.get(a, False) else CUST_CHG_METERED)
    df['ve102_dist_rate'] = DIST_RATE
    df['ve102_es_rate'] = ES_RATE
    df['ve102_rider_charge'] = rate_rider_kwh
    
    df['ve102_calculated_amount'] = df['ve102_cust_charge'] + df['usage_kwh'] * total
    df['ve102_savings'] = df['charges'] - df['ve102_calculated_amount']
    df['ve102_case_type'] = df['current_rate'].apply(
        lambda x: 'Same Schedule as Current' if x == "VE-102" else 'New Rate Schedule'
    )

    return df[['ve102_calculated_amount','ve102_savings','ve102_case_type',
               've102_cust_charge','ve102_dist_rate','ve102_es_rate','ve102_rider_charge']]

def schedule_100(usage_df: pd.DataFrame, riders_df: str = None) -> pd.DataFrame:
    # load riders row for SCHEDULE 100
    r100 = riders_df[riders_df["schedule_code"].str.contains("SCHEDULE 100", case=False, na=False)]
    if r100.empty:
        raise ValueError("No row for SCHEDULE 100 in riders file.")
    rate_rider_kwh = float(r100["rider_total_per_kwh"].iloc[0] or 0.0)
    rate_rider_kw = float(r100["rider_total_per_kw"].iloc[0] or 0.0)

    # read schedule parameters
    schedule_100 = pd.read_excel(SCHEDULES_XLSX,sheet_name="Schedule 100")
    
    # Normalize Rate column
    if "Rate" not in schedule_100.columns or schedule_100["Rate"].isna().all():
        schedule_100["Rate"] = (
            schedule_100["Rate / Description"]
            .astype(str)
            .str.replace("¢", "", regex=False)
            .str.replace("/ kWh", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.extract(r"([\d\.]+)")
            .astype(float)
        )

    def find_rows(df, billing_contains, subcat, item_contains):
        return df[
            df['Category'].astype(str).str.contains(billing_contains, case=False, na=False) &
            df['Sub-Category'].astype(str).str.contains(subcat, case=False, na=False) &
            df['Item'].astype(str).str.contains(item_contains, case=False, na=False)
        ]

    # Customer charges and distribution rates for Non-Demand vs Demand
    nondemand_cust = find_rows(schedule_100, 'Non-Demand Billing', 'Distribution', 'Basic Customer Charge')
    demand_cust = find_rows(schedule_100, 'Demand Billing', 'Distribution', 'Basic Customer Charge')
    if nondemand_cust.empty or demand_cust.empty:
        raise ValueError('Could not find both Non-Demand and Demand basic customer charge rows for Schedule 100')
    
    CUST_CHG_NONDEMAND = float(nondemand_cust['Rate'].iloc[0])
    CUST_CHG_DEMAND = float(demand_cust['Rate'].iloc[0])

    nondemand_dist = find_rows(schedule_100, 'Non-Demand Billing', 'Distribution', 'Energy Charge')
    demand_dist = find_rows(schedule_100, 'Demand Billing', 'Distribution', 'Energy Charge')
    if nondemand_dist.empty or demand_dist.empty:
        raise ValueError('Could not find both Non-Demand and Demand distribution energy charge rows for Schedule 100')
    
    DIST_RATE_NONDEMAND = float(nondemand_dist['Rate'].iloc[0]) / 100.0
    DIST_RATE_DEMAND = float(demand_dist['Rate'].iloc[0]) / 100.0

    # # ES supply energy charges
    # nondemand_es = find_rows(schedule_100, 'Non-Demand', 'ES Supply', 'Energy Charge')
    # # demand_es = find_rate(schedule_100, 'Demand Billing|Demand', 'ES Supply', 'Energy Charge')
    # # if nondemand_es.empty or demand_es.empty:
    # #     raise ValueError('Could not find both Non-Demand and Demand ES supply energy charge rows for Schedule 100')
    # ES_RATE_NONDEMAND = float(nondemand_es['Rate'].iloc[0]) / 100.0
    # # ES_RATE_DEMAND = float(demand_es['Rate'].iloc[0]) / 100.0

    # # Demand ES tiers from parameters
    # demand_es = schedule_100[ (schedule_100['Category']=='Demand Billing') & (schedule_100['Sub-Category']=='ES Supply') ]
    # def get_tier(item_name, condition):
    #     row = demand_es[
    #         (demand_es['Item']==item_name) &
    #         (demand_es['Condition / Tier']==condition)
    #     ]
    #     if row.empty:
    #         raise ValueError(f"Missing {item_name} ({condition}) in demand params")
    #     return float(row['Rate'].iloc[0]) / 100.0
    # ES_RATE_DEMAND_T1 = get_tier('Energy Tier 1', 'First 150 kWh per kW')
    # ES_RATE_DEMAND_T2 = get_tier('Energy Tier 2', 'Next 150 kWh per kW')
    # ES_RATE_DEMAND_T3 = get_tier('Energy Tier 3', 'Next 150 kWh per kW')
    # ES_RATE_DEMAND_T4 = get_tier('Energy Tier 4', 'Additional kWh')

    # ES Supply: tiered rates. Expect rows with Item like 'Energy Tier 1'..'Energy Tier 4' and Condition / Tier text
    def extract_es_tiers(df, category_contains):
        es = df[
            df["Category"].astype(str).str.contains(category_contains, case=False, na=False) &
            df["Sub-Category"].astype(str).str.contains("ES Supply", case=False, na=False)
        ]

        tiers = {}
        # CASE 1: FLAT NON-DEMAND ES RATE
        flat_rate_rows = es[es["Item"].astype(str).str.contains("Energy Charge", case=False)]
        if not flat_rate_rows.empty:
            flat_rate = float(flat_rate_rows["Rate"].iloc[0]) / 100.0
            tiers["flat"] = flat_rate
            return tiers
        
        # CASE 2: TIERED RATES
        for _, r in es.iterrows():
            cond = str(r.get("Condition / Tier", "")).lower()
            item = str(r.get("Item", "")).lower()
            rate = float(r["Rate"]) / 100.0

            if "tier 1" in item or "first" in cond:
                tiers[1] = rate
            elif "tier 2" in item or ("next" in cond and "150" in cond and 1 in tiers):
                tiers[2] = rate
            elif "tier 3" in item or ("next" in cond and "150" in cond and 2 in tiers):
                tiers[3] = rate
            elif "tier 4" in item or "additional" in cond:
                tiers[4] = rate

        return tiers

    es_tiers_nondemand = extract_es_tiers(schedule_100, "Non-Demand Billing")
    es_tiers_demand    = extract_es_tiers(schedule_100, "Demand Billing")

    # if not es_tiers_nondemand or 1 not in es_tiers_demand:
    #     raise ValueError("Missing ES tier definitions in Schedule 100.")

    # # --- fallback when demand ES supply has no tiers ---
    # # If demand has no tiered rows, try to find a flat ES energy charge row
    # if not es_tiers_nondemand:
    #     flat_es = schedule_100[
    #         schedule_100['Category'].astype(str).str.contains('Non-Demand Billing', case=False, na=False) &
    #         schedule_100['Sub-Category'].astype(str).str.contains('ES Supply', case=False, na=False) &
    #         schedule_100['Item'].astype(str).str.contains('Energy Charge', case=False, na=False)
    #     ]
    #     if not flat_es.empty:
    #         # take the first matching row as the flat ES rate
    #         flat_row = flat_es.iloc[0]
    #         flat_rate = float(flat_row['Rate']) / 100.0
    #         es_tiers_demand = {'flat_per_kwh': flat_rate}
    # # --- end fallback ---


    # Determine per-account billing type: Non-Demand if for the current and previous 11 months
    # each month's usage_kwh <= 9999
    u = usage_df.copy()
    if 'bill_period_end' in u.columns:
        u['bill_period_end'] = pd.to_datetime(u['bill_period_end'], errors='coerce')

    if 'bill_period_end' in u.columns and u['bill_period_end'].notna().any():
        max_dates = u.groupby('contract_account', dropna=False)['bill_period_end'].max().rename('max_bill').reset_index()
        u = u.merge(max_dates, on='contract_account', how='left')
        u['in_last_12m'] = u['bill_period_end'] >= (u['max_bill'] - pd.Timedelta(days=365))
    else:
        u['_row_order'] = range(len(u))
        u['in_last_12m'] = False
        for acct, grp in u.groupby('contract_account'):
            last12 = grp.sort_values('_row_order').tail(12).index
            u.loc[last12, 'in_last_12m'] = True

    # acct_flags = u[u['in_last_12m']].groupby('contract_account')['usage_kwh'].apply(lambda s: (s <= 9999).all()).rename('all_le_9999').reset_index()
    acct_flags = (
        u[u["in_last_12m"]]
        .groupby("contract_account")["usage_kwh"]
        .apply(lambda s: (s < 10000).all())     # True = all < 10k → Non-Demand
        .rename("is_nondemand")
    )
    # flag_map = {row['contract_account']: row['all_le_9999'] for _, row in acct_flags.iterrows()}

    df = usage_df.copy()
    # df['is_nondemand'] = df['contract_account'].map(lambda a: flag_map.get(a, False))
    df["is_nondemand"] = df["contract_account"].map(acct_flags).fillna(True)
    

    def compute_es_charge(row):
        usage = float(row["usage_kwh"] or 0.0)

        # Non-Demand: flat rate applies to all kWh
        if row["is_nondemand"]:
            if "flat" in es_tiers_nondemand:
                return usage * es_tiers_nondemand["flat"]
            elif 1 in es_tiers_nondemand:
                return usage * es_tiers_nondemand[1]
            else:
                return 0.0  # failsafe

        # Demand: fixed 150 kWh tier buckets
        tiers = es_tiers_demand
        if "flat" in tiers:
            return usage * tiers["flat"]

        remaining = usage
        charge = 0.0
        BUCKET = 150

        for t in (1, 2, 3, 4):
            if remaining <= 0:
                break

            rate = tiers.get(t)
            if not rate:
                continue

            cap = BUCKET if t in (1, 2, 3) else float("inf")
            take = min(remaining, cap)

            charge += take * rate
            remaining -= take

        return charge

    df["ve100_cust_charge"] = df["is_nondemand"].map(
        lambda x: CUST_CHG_NONDEMAND if x else CUST_CHG_DEMAND)
    df["ve100_dist_rate"] = df["is_nondemand"].map(
        lambda x: DIST_RATE_NONDEMAND if x else DIST_RATE_DEMAND
    )
    df["ve100_dist_charge"] = df["ve100_dist_rate"] * df["usage_kwh"]

    df["ve100_es_charge"] = df.apply(compute_es_charge, axis=1)

    # df["ve100_rider_charge"] = (
    #     df["usage_kwh"] * rate_rider_kwh +
    #     df.get("demand_kw", 0) * rate_rider_kw  ### Riders charge include demand component
    # )
    
    # For Non-Demand Billing, the rate_rider_kw component must not apply  
    df["ve100_rider_charge"] = df.apply(
    lambda row: (
        row["usage_kwh"] * rate_rider_kwh +
        (row["demand_kw"] * rate_rider_kw if not row["is_nondemand"] else 0)
    ),axis=1)

    df["ve100_calculated_amount"] = (
        df["ve100_cust_charge"] +
        df["ve100_dist_charge"] +
        df["ve100_es_charge"] +
        df["ve100_rider_charge"]
    )
    
    df['ve100_savings'] = df['charges'] - df['ve100_calculated_amount']
    df['ve100_case_type'] = df['current_rate'].apply(lambda x: 'Same Schedule as Current' if x == 'VE-100' else 'New Rate Schedule')
    
    # print(df[['ve100_calculated_amount']].head())
    # print("\nDEBUG — Schedule 100 inputs:")
    # print("Cust:", df["ve100_cust_charge"].head())
    # print("Dist:", df["ve100_dist_charge"].head())
    # print("ES  :", df["ve100_es_charge"].head())
    # print("Rider:", df["ve100_rider_charge"].head())

    # expose rider per-kwh rate so UI can display it
    return df[['ve100_calculated_amount', 've100_savings', 've100_case_type',
               've100_cust_charge', 've100_dist_rate', 've100_es_charge', 've100_rider_charge']]


def schedule_110(usage_df: pd.DataFrame, riders_df: pd.DataFrame) -> pd.DataFrame:
    """
    Tariff-accurate billing engine for Schedule 110.
    Handles:
        - Non-Demand Billing (flat ES, seasonal)
        - Demand Billing (tiered ES, seasonal, fixed 150-kWh buckets)
        - Riders (kW rider suppressed for non-demand)
        - Distribution charges
        - Customer charges
    """

    # ---------------------------------------------------------
    # 1. Load riders row
    # ---------------------------------------------------------
    r110 = riders_df[riders_df["schedule_code"]
                     .str.contains("SCHEDULE 110", case=False, na=False)]
    if r110.empty:
        raise ValueError("No row for SCHEDULE 110 in riders file.")

    rate_rider_kwh = float(r110["rider_total_per_kwh"].iloc[0] or 0.0)
    rate_rider_kw  = float(r110["rider_total_per_kw"].iloc[0] or 0.0)

    # ---------------------------------------------------------
    # 2. Load schedule 110 Excel sheet
    # ---------------------------------------------------------
    schedule_110 = pd.read_excel(SCHEDULES_XLSX, sheet_name="Schedule 110")

    # Safely convert "Rate / Description" → numeric ¢/kWh
    schedule_110["Rate"] = (
        schedule_110["Rate / Description"]
        .astype(str)
        .str.replace("¢", "", regex=False)
        .str.replace("/ kWh", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.extract(r"([\d\.]+)")
        .astype(float)
    ) / 100.0  # convert to dollars

    def find_rows(df, category, subcat, item_contains):
        return df[
            df["Category"].astype(str).str.contains(category, case=False, na=False, regex=False) &
            df["Sub-Category"].astype(str).str.contains(subcat, case=False, na=False, regex=False) &
            df["Item"].astype(str).str.contains(item_contains, case=False, na=False, regex=False)
        ]

    # ---------------------------------------------------------
    # 3. Extract Non-Demand & Demand Customer + Distribution rates
    # ---------------------------------------------------------
    nondemand_cust = find_rows(schedule_110, "Non-Demand Billing", "Distribution", "Basic Customer Charge")
    demand_cust    = find_rows(schedule_110, "Demand Billing", "Distribution", "Basic Customer Charge")

    if nondemand_cust.empty or demand_cust.empty:
        raise ValueError("Missing customer charge rows for Schedule 110.")

    CUST_CHG_NONDEMAND = float(nondemand_cust["Rate"].iloc[0])
    CUST_CHG_DEMAND    = float(demand_cust["Rate"].iloc[0])

    nondemand_dist = find_rows(schedule_110, "Non-Demand Billing", "Distribution", "Energy Charge")
    demand_dist    = find_rows(schedule_110, "Demand Billing", "Distribution", "Energy Charge")

    DIST_RATE_NONDEMAND = float(nondemand_dist["Rate"].iloc[0]) / 100.0
    DIST_RATE_DEMAND    = float(demand_dist["Rate"].iloc[0]) / 100.0

    # ---------------------------------------------------------
    # 4. ES Supply Rates (Seasonal) — Non-Demand (flat)
    # ---------------------------------------------------------
    # nondemand_es_summer = find_rows(sched, "Non-Demand Billing", "ES Supply", "Energy Charge (Summer)")
    # nondemand_es_base   = find_rows(sched, "Non-Demand Billing", "ES Supply", "Energy Charge (Base)")

    # ES_NONDEMAND_SUMMER = float(nondemand_es_summer["Rate"].iloc[0]) / 100.0
    # ES_NONDEMAND_BASE   = float(nondemand_es_base["Rate"].iloc[0]) / 100.0

    ES_NONDEMAND_SUMMER = float(schedule_110[(schedule_110["Item"]=="Energy Charge (Summer)")]["Rate"].iloc[0])
    ES_NONDEMAND_BASE = float(schedule_110[(schedule_110["Item"]=="Energy Charge (Base)")]["Rate"].iloc[0]
)

    # ---------------------------------------------------------
    # 5. ES Supply Tiers — Demand Billing (Seasonal)
    # ---------------------------------------------------------
    def extract_tiers(df, prefix):
        tiers = {}
        for i in range(1, 5):
            item = f"{prefix} Tier {i}"
            row = df[df["Item"] == item]
            if row.empty:
                raise ValueError(f"Missing {item} in Schedule 110.")
            tiers[i] = float(row["Rate"].iloc[0]) / 100.0
        return tiers

    demand_es_summer_df = schedule_110[
        (schedule_110["Category"] == "Demand Billing") &
        (schedule_110["Sub-Category"] == "ES Supply") &
        (schedule_110["Item"].str.contains("Summer", case=False, na=False))
    ]

    demand_es_base_df = schedule_110[
        (schedule_110["Category"] == "Demand Billing") &
        (schedule_110["Sub-Category"] == "ES Supply") &
        (schedule_110["Item"].str.contains("Base", case=False, na=False))
    ]

    ES_DEMAND_SUMMER = extract_tiers(demand_es_summer_df, "Summer")
    ES_DEMAND_BASE   = extract_tiers(demand_es_base_df, "Base")

    # ---------------------------------------------------------
    # 6. Determine Non-Demand vs Demand Billing
    # ---------------------------------------------------------
    u = usage_df.copy()

    if "bill_period_end" in u.columns:
        u["bill_period_end"] = pd.to_datetime(u["bill_period_end"], errors="coerce")

    if "bill_period_end" in u.columns and u["bill_period_end"].notna().any():
        max_dates = u.groupby("contract_account")["bill_period_end"].max().rename("max_bill")
        u = u.join(max_dates, on="contract_account")
        u["in_last_12m"] = u["bill_period_end"] >= (u["max_bill"] - pd.Timedelta(days=365))
    else:
        u["_row"] = range(len(u))
        u["in_last_12m"] = False
        for acct, grp in u.groupby("contract_account"):
            idx = grp.sort_values("_row").tail(12).index
            u.loc[idx, "in_last_12m"] = True

    acct_flags = (
        u[u["in_last_12m"]]
        .groupby("contract_account")["usage_kwh"]
        .apply(lambda s: (s < 10000).all())
        .rename("is_nondemand")
    )

    df = usage_df.copy()
    df["is_nondemand"] = df["contract_account"].map(acct_flags).fillna(True)

    # ---------------------------------------------------------
    # 7. ES Charge Calculator (Seasonal + Tiered/Flat)
    # ---------------------------------------------------------
    SUMMER_MONTHS = {6, 7, 8, 9}   # June–Sept
    BUCKET = 150

    def compute_es_charge(row):
        usage = float(row["usage_kwh"] or 0.0)
        month = pd.to_datetime(row["bill_period_end"]).month
        is_summer = month in SUMMER_MONTHS

        # -------- Non-Demand Billing --------
        if row["is_nondemand"]:
            rate = ES_NONDEMAND_SUMMER if is_summer else ES_NONDEMAND_BASE
            return usage * rate

        # -------- Demand Billing (Tiered, Fixed Buckets) --------
        tiers = ES_DEMAND_SUMMER if is_summer else ES_DEMAND_BASE
        remaining = usage
        charge = 0.0

        for t in (1, 2, 3, 4):
            rate = tiers[t]
            cap = BUCKET if t in (1, 2, 3) else float("inf")
            take = min(remaining, cap)
            charge += take * rate
            remaining -= take
            if remaining <= 0:
                break

        return charge

    df["ve110_es_charge"] = df.apply(compute_es_charge, axis=1)

    # ---------------------------------------------------------
    # 8. Customer, Distribution, Riders, Total Charges
    # ---------------------------------------------------------
    df["ve110_cust_charge"] = df["is_nondemand"].map(
        lambda x: CUST_CHG_NONDEMAND if x else CUST_CHG_DEMAND
    )

    df["ve110_dist_rate"] = df["is_nondemand"].map(
        lambda x: DIST_RATE_NONDEMAND if x else DIST_RATE_DEMAND
    )
    df["ve110_dist_charge"] = df["ve110_dist_rate"] * df["usage_kwh"]

    df["ve110_rider_charge"] = df.apply(
        lambda row: (
            row["usage_kwh"] * rate_rider_kwh +
            (row["demand_kw"] * rate_rider_kw if not row["is_nondemand"] else 0)
        ),
        axis=1
    )

    df["ve110_calculated_amount"] = (
        df["ve110_cust_charge"] +
        df["ve110_dist_charge"] +
        df["ve110_es_charge"] +
        df["ve110_rider_charge"]
    )

    df['ve110_savings'] = df['charges'] - df['ve110_calculated_amount']
    df['ve110_case_type'] = df['current_rate'].apply(
        lambda x: 'Same Schedule as Current' if x == 'VE-110' else 'New Rate Schedule'
    )

    # expose rider per-kwh rate for UI
    # df.to_excel(os.path.join(BASE_DIR, "ve110_debug_output.xlsx"), index=False)
    
    return df[["ve110_calculated_amount", "ve110_savings", "ve110_case_type",
               "ve110_cust_charge", "ve110_dist_rate", "ve110_es_charge", "ve110_rider_charge"]]

# register it
SCHEDULE_FUNCS = {
'120': schedule_120,
'154': schedule_154,
'102': schedule_102,
'100': schedule_100,
'110': schedule_110
}

# ==== MAIN ====
def main():
    # 1. load base once
    try:
        usage_df = load_usage(USAGE_PATH)
    except Exception as e:
        print(f"ERROR loading usage: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        riders_df = load_riders(RIDERS_PATH)
    except Exception as e:
        print(f"ERROR loading riders: {e}", file=sys.stderr)
        sys.exit(1)
    
    combined = usage_df.copy()

    # 2. run each schedule
    for sid, func in SCHEDULE_FUNCS.items():
        # out_dir = os.path.join(OUTPUT_PATH, f"ve{sid}")
        # os.makedirs(out_dir, exist_ok=True)

        try:
            result = func(usage_df,riders_df)
        except Exception as e:
            print(f"SKIP {sid}: {e}", file=sys.stderr)
            continue
        
        combined = pd.concat([combined, result], axis=1)

        # 3. write timestamped Excel
        # ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # fname = f"ve{sid}_results_{ts}.xlsx"
        # path = os.path.join(out_dir, fname)
        combined.to_excel(OUTPUT_PATH, index=False)
        print(f"Schedule {sid} done")

    print("All schedules completed.")

if __name__ == "__main__":
    main()
