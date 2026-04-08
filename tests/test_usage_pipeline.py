"""Tests for pivoted Excel → usage DataFrame (charges coalesce, demand)."""

import numpy as np
import pandas as pd
import pytest

from backend.usage_pipeline import pivoted_to_usage_df


@pytest.fixture
def profile() -> dict:
    return {
        "ACCOUNT NO.": "5000",
        "Account Profile": "Test Customer",
        "Current Rate": "VE-130",
        "Service Address": "123 Main",
    }


def test_charges_prefers_total_when_present(profile):
    df = pd.DataFrame(
        {
            "Year": [2024],
            "Month": ["JAN"],
            "Bill To": ["01/31/24"],
            "Total Consumption": [1000],
            "Demand": [50],
            "** Total Charges": ["$200.00"],
            "* Subtotal": ["$199.00"],
            "Billed Rate": ["VE-100"],
        }
    )
    out = pivoted_to_usage_df(df, profile)
    assert len(out) == 1
    assert out["charges"].iloc[0] == pytest.approx(200.0)
    assert out["demand_kw"].iloc[0] == pytest.approx(50.0)


def test_charges_falls_back_to_subtotal_when_total_missing(profile):
    """Matches Dominion PDFs where ** Total Charges is empty but * Subtotal is filled."""
    df = pd.DataFrame(
        {
            "Year": [2023, 2024],
            "Month": ["APR", "JAN"],
            "Bill To": ["04/10/23", "01/05/24"],
            "Total Consumption": [27361, 33341],
            "Demand": [104, 83],
            "** Total Charges": [np.nan, "$3966.2"],
            "* Subtotal": ["$4000.25", "$3966.2"],
            "Billed Rate": ["VE-130", "VE-130"],
        }
    )
    out = pivoted_to_usage_df(df, profile)
    assert len(out) == 2
    assert out["charges"].iloc[0] == pytest.approx(4000.25)
    assert out["charges"].iloc[1] == pytest.approx(3966.2)
    assert out["demand_kw"].iloc[0] == pytest.approx(104.0)


def test_demand_defaults_zero_without_column(profile):
    df = pd.DataFrame(
        {
            "Year": [2024],
            "Month": ["FEB"],
            "Bill To": ["02/28/24"],
            "Total Consumption": [100],
            "** Total Charges": ["$10.00"],
            "Billed Rate": ["VE-100"],
        }
    )
    out = pivoted_to_usage_df(df, profile)
    assert out["demand_kw"].iloc[0] == 0.0


def test_contract_account_from_profile_when_not_in_pivot(profile):
    """Pivoted extract often has no contract column; profile ACCOUNT NO. is used."""
    df = pd.DataFrame(
        {
            "Year": [2024],
            "Month": ["MAR"],
            "Bill To": ["03/31/24"],
            "Total Consumption": [500],
            "** Total Charges": ["$50"],
            "Billed Rate": ["VE-100"],
        }
    )
    out = pivoted_to_usage_df(df, profile)
    assert out["contract_account"].iloc[0] == "5000"
