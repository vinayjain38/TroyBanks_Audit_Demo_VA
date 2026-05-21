from pathlib import Path
import sys
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from sqlalchemy import create_engine, text

from src.Utils import upload


@patch("src.Utils.upload._ensure_reference_columns")
@patch("src.Utils.upload.pd.read_excel")
def test_upload_tariffs_versioned_writes_versioned_rows(
    mock_read_excel, mock_ensure_reference_columns, tmp_path
):
    schedule_100 = pd.DataFrame(
        {
            "Category": ["Distribution"],
            "Sub-Category": ["Energy Charge"],
            "Item": ["Rate"],
            "Condition / Tier": [""],
            "Rate / Description": ["Test"],
            "Rate": ["1.234"],
            "Description": ["Test"],
        }
    )
    schedule_120 = pd.DataFrame(
        {
            "Category": ["Distribution"],
            "Sub-Category": ["Energy Charge"],
            "Item": ["Rate"],
            "Condition / Tier": [""],
            "Rate / Description": ["Test"],
            "Rate": ["2.345"],
            "Description": ["Test"],
        }
    )
    mock_read_excel.return_value = {"Schedule 100": schedule_100, "Schedule 120": schedule_120}

    sqlite_path = tmp_path / "upload_tariffs.db"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    upload.engine = engine

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE tariff_rates (schedule_code TEXT, version INTEGER, category TEXT, sub_category TEXT, item TEXT, condition_tier TEXT, rate_description TEXT, rate TEXT, description TEXT, effective_date DATE)"
        ))

    upload.upload_tariffs_versioned("dummy.xlsx", effective_date="2025-01-01")

    result = pd.read_sql("SELECT * FROM tariff_rates", con=engine)
    assert len(result) == 2
    assert set(result["version"]) == {1}
    assert str(result["effective_date"].iloc[0]) == "2025-01-01"
    assert result["schedule_code"].tolist() == ["100", "120"]


@patch("src.Utils.upload._ensure_reference_columns")
@patch("src.Utils.upload.pd.read_excel")
def test_upload_riders_versioned_writes_versioned_rows(
    mock_read_excel, mock_ensure_reference_columns, tmp_path
):
    riders = pd.DataFrame(
        {
            "RATE SCHEDULE": ["SCHEDULE 100"],
            "T-CM": ["0.001"],
            "B-CM": ["0.002"],
            "BW-CM": ["0.003"],
            "GV-CM": ["0.004"],
            "US2-CM": ["0.005"],
            "US3-CM": ["0.006"],
            "US4-CM": ["0.007"],
            "RPS-CM": ["0.008"],
            "CE-CM": ["0.009"],
            "RBB-CM": ["0.010"],
            "E-CM": ["0.011"],
        }
    )
    mock_read_excel.return_value = riders

    sqlite_path = tmp_path / "upload_riders.db"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    upload.engine = engine

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE rider_rates (rate_schedule TEXT, t_cm TEXT, b_cm TEXT, bw_cm TEXT, gv_cm TEXT, us2_cm TEXT, us3_cm TEXT, us4_cm TEXT, rps_cm TEXT, ce_cm TEXT, rbb_cm TEXT, e_cm TEXT, version INTEGER, effective_date DATE)"
        ))

    upload.upload_riders_versioned("dummy.xlsx", effective_date="2025-02-01")

    result = pd.read_sql("SELECT * FROM rider_rates", con=engine)
    assert len(result) == 1
    assert result["version"].iloc[0] == 1
    assert str(result["effective_date"].iloc[0]) == "2025-02-01"
    assert result["rate_schedule"].iloc[0] == "SCHEDULE 100"
