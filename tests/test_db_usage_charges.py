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


@patch("backend.db_usage.pd.read_sql")
@patch("backend.db_usage.engine")
def test_fetch_uploaded_bill_options_includes_rows_with_missing_uploaded_at(mock_engine, mock_read_sql):
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    from backend.db_usage import fetch_uploaded_bill_options

    mock_read_sql.return_value = pd.DataFrame(
        {
            "accountNumber": ["TEST", "009028500412", "009028500412"],
            "accountName": ["Test Account", "County", "County"],
            "year": [2024, 2023, 2024],
            "batch_id": ["test-123", "batch-a", "batch-a"],
            "source_pdf": ["", "Profile0412.pdf", "Profile0412.pdf"],
            "uploaded_at": ["2024-01-01T00:00:00", pd.NA, pd.NA],
        }
    )
    result = fetch_uploaded_bill_options()
    assert not result.empty
    assert set(result["account_number"]) == {"009028500412"}
    assert result[result["account_number"] == "009028500412"].shape[0] == 2
    assert pd.isna(result.loc[result["account_number"] == "009028500412", "uploaded_at"]).all()


@patch("backend.db_usage.pd.read_sql")
@patch("backend.db_usage.engine")
def test_fetch_uploaded_bill_options_cleans_batch_ids(mock_engine, mock_read_sql):
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    from backend.db_usage import fetch_uploaded_bill_options

    mock_read_sql.return_value = pd.DataFrame(
        {
            "accountNumber": ["008980201225"],
            "accountName": ["COUNTY OF NEW KENT"],
            "year": [2023],
            "batch_id": ["5dce2126-73bd-52ea-bc08-b1d50d09b76\nb"],
            "source_pdf": ["8980201225  EAP Report.pdf"],
            "uploaded_at": ["2026-05-21T11:36:10.286707"],
        }
    )
    result = fetch_uploaded_bill_options()
    assert result["batch_id"].iloc[0] == "5dce2126-73bd-52ea-bc08-b1d50d09b76b"
