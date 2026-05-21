"""usage_bill queries and transforms (aligned with frontend/streamlit3.py usage merges)."""

from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text

from src.Utils.database import engine


def _normalize_bill_date(value):
    if pd.isna(value):
        return pd.NaT
    s = str(value).strip()
    if not s:
        return pd.NaT
    if s.isdigit() and len(s) == 8:
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def _parse_money_to_float(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def _parse_money_numeric(series: pd.Series) -> pd.Series:
    """Like _parse_money_to_float but keeps NaN for missing cells (for per-row coalesce)."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def fetch_uploaded_bill_options() -> pd.DataFrame:
    with engine.connect() as conn:
        raw = pd.read_sql(text('SELECT * FROM usage_bill WHERE "accountNumber" IS NOT NULL'), conn)

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "batch_id",
                "source_pdf",
                "account_number",
                "customer_name",
                "bill_year",
                "uploaded_at",
                "row_count",
            ]
        )

    if "accountName" in raw.columns:
        customer = raw["accountName"].fillna("")
    elif "CompanyName" in raw.columns:
        customer = raw["CompanyName"].fillna("")
    else:
        customer = pd.Series(["Unknown Customer"] * len(raw))

    if "year" in raw.columns:
        bill_year = raw["year"].astype(str)
    else:
        bill_year = pd.Series(["Unknown"] * len(raw))

    batch_col = (
        raw["batch_id"].fillna("").astype(str).str.strip()
        if "batch_id" in raw.columns
        else pd.Series([""] * len(raw), index=raw.index)
    )
    src_pdf = (
        raw["source_pdf"].fillna("").astype(str)
        if "source_pdf" in raw.columns
        else pd.Series([""] * len(raw), index=raw.index)
    )

    if "uploaded_at" in raw.columns:
        uploaded_at = pd.to_datetime(raw["uploaded_at"], format="mixed", errors="coerce")
        if getattr(uploaded_at.dtype, "tz", None) is not None:
            uploaded_at = uploaded_at.dt.tz_localize(None)
    else:
        uploaded_at = pd.Series([pd.NaT] * len(raw), index=raw.index)

    grouped = pd.DataFrame(
        {
            "batch_id": batch_col,
            "source_pdf": src_pdf,
            "account_number": raw["accountNumber"].astype(str).str.strip(),
            "customer_name": customer.astype(str).replace("", "Unknown Customer"),
            "bill_year": bill_year,
            "uploaded_at": uploaded_at,
        }
    )
    grouped["row_count"] = 1
    grouped = (
        grouped.groupby(
            ["batch_id", "source_pdf", "account_number", "customer_name", "bill_year"],
            as_index=False,
            dropna=False,
        )
        .agg(uploaded_at=("uploaded_at", "max"), row_count=("row_count", "sum"))
        .sort_values(["uploaded_at", "account_number", "bill_year"], ascending=[False, True, True], na_position="last")
        .reset_index(drop=True)
    )
    return grouped


def _load_profile_json_from_usage_bill(account_number: str, batch_id: str) -> dict | None:
    if not str(batch_id).strip():
        return None
    q = text("""
        SELECT account_profile_json FROM usage_bill
        WHERE "accountNumber" = :an AND batch_id = :bid
          AND account_profile_json IS NOT NULL AND TRIM(account_profile_json) <> ''
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(q, {"an": str(account_number).strip(), "bid": str(batch_id).strip()}).fetchone()
    if not row or row[0] is None:
        return None
    try:
        out = json.loads(row[0])
        return out if isinstance(out, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def fetch_saved_bill_profile(account_number: str, batch_ids: Optional[list[str]] = None) -> dict:
    """Profile dict from PDF OCR stored on upload; newest upload among matching batches wins."""
    opts = fetch_uploaded_bill_options()
    opts = opts[opts["account_number"].astype(str).str.strip() == str(account_number).strip()]
    if opts.empty:
        return {}
    if batch_ids:
        bs = {str(b).strip() for b in batch_ids if str(b).strip()}
        opts = opts[opts["batch_id"].astype(str).str.strip().isin(bs)]
    if opts.empty:
        return {}
    opts = opts.sort_values("uploaded_at", ascending=False, na_position="last")
    bid = str(opts.iloc[0]["batch_id"]).strip()
    if not bid:
        return {}
    prof = _load_profile_json_from_usage_bill(account_number, bid)
    return prof if isinstance(prof, dict) else {}


def fetch_version_options(table_name: str) -> pd.DataFrame:
    query = text(f"""
        SELECT version, MAX(effective_date) AS effective_date, MAX(uploaded_at) AS uploaded_at
        FROM {table_name}
        GROUP BY version
        ORDER BY version DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def load_usage_from_db(
    account_number: str,
    bill_year: str,
    uploaded_at=None,
    batch_id: Optional[str] = None,
) -> pd.DataFrame:
    bid = str(batch_id).strip() if batch_id is not None and str(batch_id).strip() else None

    if bid:
        query = text("""
            SELECT *
            FROM usage_bill
            WHERE "accountNumber" = :account_number
              AND CAST("year" AS TEXT) = :bill_year
              AND batch_id = :batch_id
            ORDER BY "bill_to_raw"
        """)
        params: dict[str, Any] = {
            "account_number": account_number,
            "bill_year": str(bill_year),
            "batch_id": bid,
        }
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params)
    elif uploaded_at is not None and not pd.isna(uploaded_at):
        query = text("""
            SELECT *
            FROM usage_bill
            WHERE "accountNumber" = :account_number
              AND CAST("year" AS TEXT) = :bill_year
              AND "uploaded_at" = :uploaded_at
            ORDER BY "bill_to_raw"
        """)
        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                conn,
                params={
                    "account_number": account_number,
                    "bill_year": str(bill_year),
                    "uploaded_at": pd.to_datetime(uploaded_at),
                },
            )
    else:
        query = text("""
            SELECT *
            FROM usage_bill
            WHERE "accountNumber" = :account_number
              AND CAST("year" AS TEXT) = :bill_year
            ORDER BY "bill_to_raw"
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"account_number": account_number, "bill_year": str(bill_year)})

    if df.empty:
        return pd.DataFrame(
            columns=[
                "contract_account",
                "customer",
                "current_rate",
                "bill_period_end",
                "usage_kwh",
                "demand_kw",
                "charges",
            ]
        )

    customer_col = (
        "accountName"
        if "accountName" in df.columns
        else ("CompanyName" if "CompanyName" in df.columns else None)
    )
    customer_val = (
        str(df[customer_col].dropna().iloc[0]).strip()
        if customer_col and not df[customer_col].dropna().empty
        else "Unknown Customer"
    )

    out = pd.DataFrame()
    out["contract_account"] = df["accountNumber"].astype(str).str.strip()
    out["customer"] = customer_val
    billed_rate = df["billed_rate"] if "billed_rate" in df.columns else pd.Series([""] * len(df))
    out["current_rate"] = billed_rate.astype(str)
    out["bill_period_end"] = (
        df["bill_to_raw"].apply(_normalize_bill_date) if "bill_to_raw" in df.columns else pd.Series(pd.NaT, index=df.index)
    )
    out["usage_kwh"] = (
        pd.to_numeric(df["total_consumption"], errors="coerce").fillna(0.0)
        if "total_consumption" in df.columns
        else 0.0
    )
    out["demand_kw"] = pd.to_numeric(df["demand"], errors="coerce").fillna(0.0) if "demand" in df.columns else 0.0
    charge_parts: list[pd.Series] = []
    if "total_charges_raw" in df.columns:
        charge_parts.append(_parse_money_numeric(df["total_charges_raw"]))
    if "subtotal_raw" in df.columns:
        charge_parts.append(_parse_money_numeric(df["subtotal_raw"]))
    if charge_parts:
        ch = charge_parts[0]
        for p in charge_parts[1:]:
            ch = ch.fillna(p)
        out["charges"] = ch.fillna(0.0)
    else:
        out["charges"] = 0.0
    out = out.dropna(subset=["bill_period_end"]).sort_values("bill_period_end").reset_index(drop=True)
    return out


def load_usage_merged_for_account(account_number: str, batch_rows: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(
        columns=[
            "contract_account",
            "customer",
            "current_rate",
            "bill_period_end",
            "usage_kwh",
            "demand_kw",
            "charges",
        ]
    )
    if batch_rows is None or batch_rows.empty:
        return empty

    rows_sorted = batch_rows.sort_values("uploaded_at", ascending=True, na_position="first")
    frames: list[pd.DataFrame] = []
    for _, brow in rows_sorted.iterrows():
        by = str(brow["bill_year"])
        bid_val = brow.get("batch_id")
        bid = str(bid_val).strip() if bid_val is not None and pd.notna(bid_val) and str(bid_val).strip() else ""
        if bid:
            part = load_usage_from_db(account_number, by, batch_id=bid)
        else:
            part = load_usage_from_db(account_number, by, uploaded_at=brow.get("uploaded_at"))
        if part is not None and not part.empty:
            frames.append(part)

    if not frames:
        return empty

    out = pd.concat(frames, ignore_index=True)
    out["bill_period_end"] = pd.to_datetime(out["bill_period_end"], errors="coerce")
    out = out.dropna(subset=["bill_period_end"]).sort_values("bill_period_end")
    out = out.drop_duplicates(subset=["bill_period_end"], keep="last")
    return out.reset_index(drop=True)


def load_tariff_workbook_for_version(version: int):
    from pathlib import Path

    from src.Utils.paths import TARIFF_UPLOAD_DIR

    query = text("""
        SELECT id, schedule_code, category, sub_category, item, condition_tier, rate_description, rate, description
        FROM tariff_rates
        WHERE version = :version
        ORDER BY schedule_code, id
    """)
    with engine.connect() as conn:
        tariff_df = pd.read_sql(query, conn, params={"version": int(version)})

    if tariff_df.empty:
        raise ValueError(f"No tariff rows found for version {version}")

    tmp_dir = TARIFF_UPLOAD_DIR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = tmp_dir / f"tariffs_version_{version}.xlsx"

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for schedule_code, group in tariff_df.groupby("schedule_code"):
            sheet_name = f"Schedule {str(schedule_code).strip()}"
            out = group.rename(
                columns={
                    "category": "Category",
                    "sub_category": "Sub-Category",
                    "item": "Item",
                    "condition_tier": "Condition / Tier",
                    "rate_description": "Rate / Description",
                    "rate": "Rate",
                    "description": "Description",
                }
            )
            cols = ["Category", "Sub-Category", "Item", "Condition / Tier", "Rate / Description", "Rate", "Description"]
            out = out[[c for c in cols if c in out.columns]]
            out.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    return workbook_path


def load_riders_for_version(version: int) -> pd.DataFrame:
    query = text("""
        SELECT
            rate_schedule,
            t_cm, b_cm, bw_cm, gv_cm, us2_cm, us3_cm, us4_cm, rps_cm, ce_cm, rbb_cm, e_cm
        FROM rider_rates
        WHERE version = :version
        ORDER BY id
    """)
    with engine.connect() as conn:
        riders_raw = pd.read_sql(query, conn, params={"version": int(version)})

    if riders_raw.empty:
        raise ValueError(f"No rider rows found for version {version}")

    rider_cols = ["t_cm", "b_cm", "bw_cm", "gv_cm", "us2_cm", "us3_cm", "us4_cm", "rps_cm", "ce_cm", "rbb_cm", "e_cm"]
    for col in rider_cols:
        riders_raw[col] = _parse_money_to_float(riders_raw[col])

    riders_out = pd.DataFrame()
    riders_out["schedule_code"] = riders_raw["rate_schedule"].astype(str)
    riders_out["rider_total_per_kwh"] = riders_raw[rider_cols].sum(axis=1)
    riders_out["rider_total_per_kw"] = 0.0
    return riders_out
