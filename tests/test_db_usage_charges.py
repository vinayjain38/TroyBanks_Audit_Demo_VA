"""Tests for DB → usage frame charge coalesce (no live Postgres)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@patch("backend.db_usage.pd.read_sql")
@patch("backend.db_usage.engine")
def test_load_usage_coalesces_subtotal_when_total_empty(mock_engine, mock_read_sql):
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    from backend.db_usage import load_usage_from_db

    mock_read_sql.return_value = pd.DataFrame(
        {
            "accountNumber": ["5000"],
            "accountName": ["Acme"],
            "year": [2023],
            "bill_to_raw": ["04/10/23"],
            "total_consumption": [27361.0],
            "billed_rate": ["VE-130"],
            "demand": [104.0],
            "total_charges_raw": [pd.NA],
            "subtotal_raw": ["$4000.25"],
        }
    )
    out = load_usage_from_db("5000", "2023")
    assert not out.empty
    assert out["charges"].iloc[0] == pytest.approx(4000.25)

    mock_read_sql.return_value = pd.DataFrame(
        {
            "accountNumber": ["5000"],
            "accountName": ["Acme"],
            "year": [2024],
            "bill_to_raw": ["01/05/24"],
            "total_consumption": [33341.0],
            "billed_rate": ["VE-130"],
            "demand": [83.0],
            "total_charges_raw": ["$3966.2"],
            "subtotal_raw": ["$3966.2"],
        }
    )
    out2 = load_usage_from_db("5000", "2024")
    assert out2["charges"].iloc[0] == pytest.approx(3966.2)
