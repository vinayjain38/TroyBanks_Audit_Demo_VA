"""Schedule merge and date display helpers work for varied bill uploads."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "frontend"))

from components.tables import (  # noqa: E402
    format_date_only_columns,
    merge_schedule_output,
    normalize_bill_period_key,
    standardize_usage_dataframe,
)


def test_normalize_bill_period_key_strips_time():
    s = pd.Series([pd.Timestamp("2025-02-20 15:30:00"), "2024-03-21 00:00:00", "TOTAL"])
    out = normalize_bill_period_key(s)
    assert out.iloc[0] == "2025-02-20"
    assert out.iloc[1] == "2024-03-21"
    assert out.iloc[2] == "TOTAL"


def test_merge_schedule_output_survives_api_row_filter():
    """API may return fewer rows than UI; merge by period must not leave trailing None."""
    base = pd.DataFrame(
        {
            "bill_period_end": pd.to_datetime(
                [f"2023-{m:02d}-15" for m in range(1, 10)]
                + [f"2024-{m:02d}-15" for m in range(1, 13)]
                + [f"2025-{m:02d}-15" for m in range(1, 11)]
            ),
            "usage_kwh": list(range(31)),
            "charges": [10.0] * 31,
        }
    )
    api_subset = base.loc[base["bill_period_end"].dt.year >= 2024].copy()
    schedule_out = api_subset.assign(ve100_calculated_amount=api_subset["charges"] * 0.9)

    merged = merge_schedule_output(
        base,
        schedule_out[["bill_period_end", "ve100_calculated_amount"]].rename(
            columns={"ve100_calculated_amount": "VE-100 Calculated ($)"}
        ),
    )
    label = "VE-100 Calculated ($)"
    y2025 = merged.loc[merged["bill_period_end"].dt.year == 2025, label]
    assert y2025.notna().all(), "2025 rows should have calculated values after merge"
    y2023 = merged.loc[merged["bill_period_end"].dt.year == 2023, label]
    assert y2023.isna().all(), "filtered-out years stay empty (no bogus positional fill)"


def test_format_date_only_columns_no_timestamp_strings():
    df = pd.DataFrame({"bill_period_end": pd.to_datetime(["2023-04-26", "2025-10-20"])})
    shown = format_date_only_columns(df)
    assert "00:00:00" not in shown["bill_period_end"].iloc[0]


def test_standardize_usage_dataframe_sorts_and_parses():
    raw = pd.DataFrame(
        {
            "bill_period_end": ["2025-10-20", "2023-04-26", "2024-01-15"],
            "usage_kwh": [100, 200, 300],
            "charges": [1, 2, 3],
        }
    )
    out = standardize_usage_dataframe(raw)
    assert out["bill_period_end"].is_monotonic_increasing
    assert str(out["bill_period_end"].iloc[0].date()) == "2023-04-26"
