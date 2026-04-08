from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.db_usage import fetch_version_options

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED = frozenset({"tariff_rates", "rider_rates"})


@router.get("/{table_name}")
def version_history(table_name: str):
    if table_name not in ALLOWED:
        raise HTTPException(status_code=400, detail="table_name must be tariff_rates or rider_rates.")
    try:
        df = fetch_version_options(table_name)
    except Exception:
        logger.exception("fetch_version_options failed for %s", table_name)
        raise HTTPException(status_code=500, detail="Version history unavailable.") from None
    if df.empty:
        return []
    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "version": int(row["version"]) if pd.notna(row["version"]) else None,
                "effective_date": str(row["effective_date"]) if pd.notna(row.get("effective_date")) else None,
                "uploaded_at": row["uploaded_at"].isoformat() if pd.notna(row.get("uploaded_at")) else None,
            }
        )
    return records
