"""Unit tests for usage upload batch metadata (no live DB required)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def minimal_pivoted_xlsx(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        {
            "Year": ["2024"],
            "Month": ["JAN"],
            "Bill From": ["01/01/24"],
            "Bill To": ["01/31/24"],
            "** Total Charges": ["$100.00"],
            "Total Consumption": ["500"],
            "Billed Rate": ["VE-100"],
        }
    )
    p = tmp_path / "usage.xlsx"
    df.to_excel(p, sheet_name="pivoted", index=False)
    return p


@patch("src.Utils.upload.engine.begin")
@patch("src.Utils.upload._ensure_usage_bill_batch_columns")
@patch("src.Utils.upload.upsert_dataframe")
def test_upload_usage_sets_batch_id_and_conflict_columns(mock_upsert, mock_ensure, mock_begin, minimal_pivoted_xlsx):
    _cm = MagicMock()
    _cm.__enter__.return_value.execute = MagicMock()
    _cm.__exit__.return_value = None
    mock_begin.return_value = _cm
    from src.Utils import upload

    upload.upload_usage_data(
        str(minimal_pivoted_xlsx),
        batch_id="test-batch-uuid",
        source_pdf="bill.pdf",
        profile={"ACCOUNT NO.": "12345", "Account Profile": "Acme LLC"},
    )

    mock_ensure.assert_called_once()
    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["unique_cols"] == ["batch_id", "bill_from_raw", "bill_to_raw"]
    out = kwargs["df"]
    assert (out["batch_id"] == "test-batch-uuid").all()
    assert (out["source_pdf"] == "bill.pdf").all()
    assert (out["accountNumber"] == "12345").all()
    assert (out["accountName"] == "Acme LLC").all()


@patch("src.Utils.upload.engine.begin")
@patch("src.Utils.upload._ensure_usage_bill_batch_columns")
@patch("src.Utils.upload.upsert_dataframe")
def test_upload_usage_fingerprint_when_batch_omitted(mock_upsert, mock_ensure, mock_begin, minimal_pivoted_xlsx):
    _cm = MagicMock()
    _cm.__enter__.return_value.execute = MagicMock()
    _cm.__exit__.return_value = None
    mock_begin.return_value = _cm
    from src.Utils import upload

    upload.upload_usage_data(str(minimal_pivoted_xlsx))
    out = mock_upsert.call_args.kwargs["df"]
    bid = out["batch_id"].iloc[0]
    assert isinstance(bid, str)
    assert len(bid) >= 32
    from uuid import UUID

    assert UUID(bid).version == 5

    upload.upload_usage_data(str(minimal_pivoted_xlsx))
    bid2 = mock_upsert.call_args.kwargs["df"]["batch_id"].iloc[0]
    assert bid == bid2


@patch("src.Utils.upload.engine.begin")
@patch("src.Utils.upload._ensure_usage_bill_batch_columns")
@patch("src.Utils.upload.upsert_dataframe")
def test_usage_batch_id_from_bytes_stable(mock_upsert, mock_ensure, mock_begin):
    _cm = MagicMock()
    _cm.__enter__.return_value.execute = MagicMock()
    _cm.__exit__.return_value = None
    mock_begin.return_value = _cm
    from src.Utils.upload import usage_batch_id_from_bytes

    a = usage_batch_id_from_bytes(b"same-bytes")
    b = usage_batch_id_from_bytes(b"same-bytes")
    c = usage_batch_id_from_bytes(b"other")
    assert a == b
    assert a != c
