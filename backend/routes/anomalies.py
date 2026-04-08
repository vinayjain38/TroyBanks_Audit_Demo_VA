from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.anomaly_service import build_usage_anomalies_df
from backend.calc_service import df_to_json_safe_records
from backend.db_usage import fetch_uploaded_bill_options, load_usage_merged_for_account

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{account_number}")
def get_anomalies(
    account_number: str,
    year: str | None = None,
    batch_id: str | None = None,
    view_start: str | None = None,
    view_end: str | None = None,
    pct_spike_limit: float = Query(0.5, ge=0.0, le=1.0),
    abs_spike_limit: float = Query(5.0, ge=0.0),
    billing_median_multiplier: float = Query(2.5, ge=1.0),
    billing_min_delta_cpk: float = Query(0.05, ge=0.0),
    billing_min_kwh: float = Query(30.0, ge=0.0),
    charge_median_multiplier: float = Query(2.5, ge=1.0),
    charge_min_usd: float = Query(100.0, ge=0.0),
):
    opts = fetch_uploaded_bill_options()
    opts = opts[opts["account_number"] == account_number]
    if opts.empty:
        raise HTTPException(status_code=404, detail="No uploaded bills for this account.")

    if year:
        opts = opts[opts["bill_year"].astype(str) == str(year)]
    if batch_id and str(batch_id).strip():
        opts = opts[opts["batch_id"].astype(str) == str(batch_id).strip()]

    merged = load_usage_merged_for_account(account_number, opts)
    if merged.empty:
        raise HTTPException(status_code=404, detail="No usage rows for anomaly detection.")

    view_period = None
    if view_start and view_end:
        view_period = pd.DataFrame({"bill_period_end": pd.to_datetime([view_start, view_end], errors="coerce")})
    elif year:
        view_period = merged[merged["bill_period_end"].dt.year.astype(str) == str(year)].copy()

    try:
        out = build_usage_anomalies_df(
            merged,
            pct_spike_limit=pct_spike_limit,
            abs_spike_limit=abs_spike_limit,
            billing_median_multiplier=billing_median_multiplier,
            billing_min_delta_cpk=billing_min_delta_cpk,
            billing_min_kwh=billing_min_kwh,
            charge_median_multiplier=charge_median_multiplier,
            charge_min_usd=charge_min_usd,
            view_period_df=view_period,
        )
    except Exception:
        logger.exception("build_usage_anomalies_df failed for account %s", account_number)
        raise HTTPException(status_code=500, detail="Anomaly processing failed.") from None

    return {"records": df_to_json_safe_records(out)}
