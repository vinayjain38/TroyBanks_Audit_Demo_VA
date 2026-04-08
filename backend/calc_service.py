"""Schedule recalculation (mirrors streamlit run_schedules_with_versions)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import src.Billing_Engine.app_new as app_new_module
from src.Billing_Engine.app_new import load_riders
from src.Utils.paths import RIDERS_OUT, SCHEDULES_XLSX

from backend.db_usage import load_riders_for_version, load_tariff_workbook_for_version


def resolve_riders_df(rider_source: str, rider_version: int | None) -> pd.DataFrame:
    if rider_source == "db" and rider_version is not None:
        return load_riders_for_version(int(rider_version))
    return load_riders(str(RIDERS_OUT))


def resolve_tariff_workbook(tariff_source: str, tariff_version: int | None) -> Path:
    if tariff_source == "db" and tariff_version is not None:
        return load_tariff_workbook_for_version(int(tariff_version))
    return Path(SCHEDULES_XLSX)


def run_schedules(
    usage_df: pd.DataFrame,
    riders_df: pd.DataFrame,
    tariff_workbook: Path,
    schedule_ids: list[str],
) -> pd.DataFrame:
    if not schedule_ids:
        raise ValueError("Select at least one schedule.")
    combined = usage_df.copy()
    original_workbook = app_new_module.SCHEDULES_XLSX
    app_new_module.SCHEDULES_XLSX = tariff_workbook
    try:
        for sid in schedule_ids:
            func = app_new_module.SCHEDULE_FUNCS.get(sid)
            if func is None:
                continue
            result = func(usage_df.copy(), riders_df.copy())
            combined = pd.concat([combined, result], axis=1)
    finally:
        app_new_module.SCHEDULES_XLSX = original_workbook

    combined = combined.loc[:, ~combined.columns.duplicated()].reset_index(drop=True)
    return combined


def df_to_json_safe_records(df: pd.DataFrame) -> list[dict]:
    """Records suitable for JSON (NaN/NaT -> None)."""
    if df.empty:
        return []
    tmp = df.copy()
    for col in tmp.columns:
        if pd.api.types.is_datetime64_any_dtype(tmp[col]):
            tmp[col] = tmp[col].dt.strftime("%Y-%m-%d")
    return tmp.astype(object).where(pd.notnull(tmp), None).to_dict(orient="records")
