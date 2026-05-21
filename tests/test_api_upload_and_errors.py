"""API tests: bill upload wiring (mocked OCR/extract) and safe error responses."""

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@patch("backend.routes.bills.upload_usage_dataframe")
@patch("backend.routes.bills.ocr_pdf_page", return_value="")
@patch("backend.routes.bills.parse_dominion_account_profile", return_value=[])
@patch("backend.routes.bills.pivot_usage_table")
@patch("backend.routes.bills.extract_all_usage_tables")
def test_upload_bill_coalesced_charges_in_response(
    mock_extract,
    mock_pivot,
    mock_parse_prof,
    mock_ocr,
    mock_upload,
    client,
    tmp_path,
    monkeypatch,
):
    import backend.routes.bills as bills_r

    monkeypatch.setattr(bills_r, "NEW_BILLS_DIR", tmp_path / "nb_in")
    monkeypatch.setattr(bills_r, "NEW_BILLS_PARSED_DIR", tmp_path / "nb_out")

    mock_extract.return_value = pd.DataFrame({"placeholder": [1]})
    mock_pivot.return_value = pd.DataFrame(
        {
            "Year": [2024],
            "Month": ["JAN"],
            "Bill To": ["01/31/24"],
            "Total Consumption": [500],
            "Demand": [12],
            "** Total Charges": [pd.NA],
            "* Subtotal": ["$42.50"],
            "Billed Rate": ["VE-100"],
        }
    )

    files = {"file": ("stub.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "application/pdf")}
    r = client.post("/api/bills/upload", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    recs = body["usage_records"]
    assert len(recs) == 1
    assert recs[0]["charges"] == pytest.approx(42.5)
    assert recs[0]["demand_kw"] == pytest.approx(12.0)
    mock_upload.assert_called_once()


@patch("backend.routes.bills.extract_all_usage_tables")
@patch("backend.routes.bills._response_for_existing_batch")
def test_upload_bill_skips_ocr_when_batch_already_exists(mock_existing, mock_extract, client):
    mock_existing.return_value = {
        "status": "success",
        "cache_hit": True,
        "account_number": "009028500412",
        "account_name": "County",
        "rows_uploaded": 12,
        "batch_id": "existing-batch",
        "usage_records": [
            {
                "contract_account": "009028500412",
                "customer": "County",
                "current_rate": "VE-100",
                "bill_period_end": "2024-01-31",
                "usage_kwh": 500,
                "demand_kw": 12,
                "charges": 42.5,
            }
        ],
        "profile": {},
    }

    files = {"file": ("stub.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "application/pdf")}
    r = client.post("/api/bills/upload", files=files)

    assert r.status_code == 200, r.text
    assert r.json()["cache_hit"] is True
    mock_existing.assert_called_once()
    mock_extract.assert_not_called()


def test_upload_rejects_non_pdf(client):
    r = client.post("/api/bills/upload", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_calculate_invalid_body_not_generic_500(client):
    """Bad request / validation should not return generic 500 'Internal server error'."""
    r = client.post("/api/calculate", json={})
    assert r.status_code in (400, 422)
    assert r.status_code != 500
    detail = r.json().get("detail", "")
    assert "Internal server error" not in str(detail)


def test_anomalies_can_compute_from_posted_usage_records(client):
    """UI anomaly tables should not depend on reloading the same account from usage_bill."""
    usage_records = [
        {
            "contract_account": "009999999999",
            "customer": "Posted Account",
            "current_rate": "VE-100",
            "bill_period_end": "2024-01-31",
            "usage_kwh": 100,
            "demand_kw": 0,
            "charges": 20,
        },
        {
            "contract_account": "009999999999",
            "customer": "Posted Account",
            "current_rate": "VE-100",
            "bill_period_end": "2024-02-29",
            "usage_kwh": 100,
            "demand_kw": 0,
            "charges": 20,
        },
        {
            "contract_account": "009999999999",
            "customer": "Posted Account",
            "current_rate": "VE-100",
            "bill_period_end": "2024-03-31",
            "usage_kwh": 100,
            "demand_kw": 0,
            "charges": 500,
        },
    ]

    r = client.post(
        "/api/anomalies",
        json={
            "usage_records": usage_records,
            "view_records": usage_records,
            "charge_min_usd": 100,
            "charge_median_multiplier": 2.5,
        },
    )

    assert r.status_code == 200, r.text
    records = r.json()["records"]
    assert records
    assert records[0]["account"] == "009999999999"
