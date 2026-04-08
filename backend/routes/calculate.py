from __future__ import annotations

import logging

import src.Billing_Engine.app_new as app_new_module
from fastapi import APIRouter, HTTPException
import pandas as pd
from pydantic import BaseModel

from backend.calc_service import (
    df_to_json_safe_records,
    resolve_riders_df,
    resolve_tariff_workbook,
    run_schedules,
)
from backend.db_usage import fetch_uploaded_bill_options, load_usage_from_db, load_usage_merged_for_account
from backend.usage_pipeline import records_to_usage_df
from src.Utils.paths import RIDERS_OUT, SCHEDULES_XLSX

router = APIRouter()
logger = logging.getLogger(__name__)


def _filter_by_period(df: pd.DataFrame, period: str | None, calendar_year: int | None) -> tuple[pd.DataFrame, str]:
    """Match streamlit filter_by_year_option for recalc."""
    if df.empty:
        return df, ""

    df = df.copy()
    df["bill_period_end"] = pd.to_datetime(df["bill_period_end"], errors="coerce")

    if period == "All Years" or (period is None and calendar_year is None):
        return df, "All Years"

    if period == "Last 12 Months":
        month_periods = df["bill_period_end"].dt.to_period("M")
        latest_month = month_periods.max()
        if pd.isna(latest_month):
            return df.iloc[0:0].copy(), "Last 12 Months"
        start_month = latest_month - 11
        mask = (month_periods >= start_month) & (month_periods <= latest_month)
        label = (
            f"Last 12 Months "
            f"({start_month.to_timestamp().strftime('%b %Y')} – {latest_month.to_timestamp().strftime('%b %Y')})"
        )
        return df[mask].copy(), label

    if calendar_year is not None:
        return df[df["bill_period_end"].dt.year == int(calendar_year)].copy(), str(calendar_year)

    return df, str(period or "")


class CalculateRequest(BaseModel):
    schedule_id: str | None = None
    schedule_ids: list[str] | None = None
    usage_records: list[dict] | None = None
    account_number: str | None = None
    batches: list[dict] | None = None
    year: str | None = None
    batch_id: str | None = None
    uploaded_at: str | None = None
    period: str | None = None
    calendar_year: int | None = None
    tariff_source: str = "file"
    tariff_version: int | None = None
    rider_source: str = "file"
    rider_version: int | None = None


@router.get("/schedules")
def list_schedules():
    return sorted(app_new_module.SCHEDULE_FUNCS.keys())


@router.get("/sources")
def calc_sources():
    from backend.db_usage import fetch_version_options

    try:
        tariff_versions = fetch_version_options("tariff_rates")
    except Exception:
        tariff_versions = pd.DataFrame()
    try:
        rider_versions = fetch_version_options("rider_rates")
    except Exception:
        rider_versions = pd.DataFrame()

    return {
        "schedules": sorted(app_new_module.SCHEDULE_FUNCS.keys()),
        "tariff_workbook_on_disk": SCHEDULES_XLSX.exists(),
        "riders_file_on_disk": RIDERS_OUT.exists(),
        "tariff_versions": tariff_versions.to_dict(orient="records") if not tariff_versions.empty else [],
        "rider_versions": rider_versions.to_dict(orient="records") if not rider_versions.empty else [],
    }


@router.post("")
def calculate(body: CalculateRequest):
    ids = list(body.schedule_ids or [])
    if body.schedule_id:
        ids = [body.schedule_id] + [x for x in ids if x != body.schedule_id]
    if not ids:
        raise HTTPException(status_code=400, detail="schedule_id or schedule_ids is required.")

    usage_df: pd.DataFrame | None = None

    if body.usage_records:
        usage_df = records_to_usage_df(body.usage_records)
    elif body.batches:
        br = pd.DataFrame(body.batches)
        needed = {"bill_year", "batch_id", "uploaded_at"} & set(br.columns)
        if "bill_year" not in br.columns:
            raise HTTPException(status_code=400, detail="batches must include bill_year.")
        usage_df = load_usage_merged_for_account(str(body.account_number), br)
    elif body.account_number and body.year:
        uploaded = pd.to_datetime(body.uploaded_at) if body.uploaded_at else None
        usage_df = load_usage_from_db(
            body.account_number,
            str(body.year),
            uploaded_at=uploaded,
            batch_id=body.batch_id,
        )
    elif body.account_number:
        opts = fetch_uploaded_bill_options()
        opts = opts[opts["account_number"] == body.account_number]
        if body.batch_id and str(body.batch_id).strip():
            opts = opts[opts["batch_id"].astype(str) == str(body.batch_id).strip()]
        usage_df = load_usage_merged_for_account(body.account_number, opts)
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide usage_records, or account_number (+ year), or account_number + batches.",
        )

    if usage_df is None or usage_df.empty:
        raise HTTPException(status_code=404, detail="No usage rows to calculate.")

    usage_df, _period_label = _filter_by_period(usage_df, body.period, body.calendar_year)
    if usage_df.empty:
        raise HTTPException(status_code=404, detail="No usage rows after period filter.")

    try:
        riders_df = resolve_riders_df(body.rider_source, body.rider_version)
        tariff_wb = resolve_tariff_workbook(body.tariff_source, body.tariff_version)
        combined = run_schedules(usage_df, riders_df, tariff_wb, ids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("calculate.run_schedules failed")
        raise HTTPException(status_code=500, detail="Calculation failed.") from None

    return {
        "records": df_to_json_safe_records(combined),
        "schedules_run": ids,
    }
