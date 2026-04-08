from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.billing_modules import (
    extract_all_usage_tables,
    ocr_pdf_page,
    parse_dominion_account_profile,
    pivot_usage_table,
)
from backend.db_usage import (
    fetch_saved_bill_profile,
    fetch_uploaded_bill_options,
    load_usage_merged_for_account,
)
from backend.calc_service import df_to_json_safe_records
from backend.usage_pipeline import pivoted_to_usage_df
from src.Utils.paths import NEW_BILLS_DIR, NEW_BILLS_PARSED_DIR
from src.Utils.upload import upload_usage_data, usage_batch_id_from_bytes

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload")
async def upload_bill(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file.")

    NEW_BILLS_DIR.mkdir(parents=True, exist_ok=True)
    NEW_BILLS_PARSED_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = os.path.basename(file.filename) or "upload.pdf"
    pdf_path = NEW_BILLS_DIR / safe_name
    content = await file.read()

    with open(pdf_path, "wb") as f:
        f.write(content)

    batch_id = usage_batch_id_from_bytes(content)

    try:
        raw_df = extract_all_usage_tables(str(pdf_path), dpi=400)
        pivoted = pivot_usage_table(raw_df)
        if pivoted is None or pivoted.empty:
            raise HTTPException(status_code=422, detail="No usage tables extracted from PDF.")

        try:
            ocr_text = ocr_pdf_page(str(pdf_path), page_index=1, dpi=400)
            pairs = parse_dominion_account_profile(ocr_text)
            profile = dict(pairs) if pairs else {}
        except Exception as exc_profile:
            logger.warning(
                "Account profile OCR/parse failed for %s: %s",
                safe_name,
                exc_profile,
                exc_info=True,
            )
            profile = {}

        stem = Path(safe_name).stem
        pivoted_path = NEW_BILLS_PARSED_DIR / f"{stem}_pivoted.xlsx"
        pivoted.to_excel(pivoted_path, sheet_name="pivoted", index=False)

        upload_usage_data(str(pivoted_path), batch_id=batch_id, source_pdf=safe_name, profile=profile or None)

        acct = str(profile.get("ACCOUNT NO.", "") or "").strip()
        name = str(profile.get("Account Profile", "") or "").strip()

        usage_df = pivoted_to_usage_df(pivoted, profile)
        if not acct and not usage_df.empty:
            acct = str(usage_df["contract_account"].iloc[0])
        if not name and not usage_df.empty:
            name = str(usage_df["customer"].iloc[0])

        return {
            "status": "success",
            "account_number": acct,
            "account_name": name,
            "rows_uploaded": int(len(pivoted)),
            "batch_id": batch_id,
            "usage_records": df_to_json_safe_records(usage_df),
            "profile": profile,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Bill upload failed for %s", safe_name)
        raise HTTPException(status_code=500, detail="Bill processing failed.") from None


@router.get("")
def list_bills():
    df = fetch_uploaded_bill_options()
    if df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        out.append(
            {
                "accountNumber": row["account_number"],
                "accountName": row["customer_name"],
                "year": row["bill_year"],
                "batch_id": row["batch_id"],
                "uploaded_at": row["uploaded_at"].isoformat() if pd.notna(row.get("uploaded_at")) else None,
                "source_pdf": row.get("source_pdf"),
                "row_count": int(row["row_count"]),
            }
        )
    return out


@router.get("/profile")
def read_saved_bill_profile(
    account_number: str = Query(..., min_length=1, description="Account number (saved bills)"),
    batch_ids: str | None = Query(None, description="Comma-separated batch UUIDs (optional)"),
):
    """OCR/profile JSON stored at upload (`usage_bill.account_profile_json`). Used by Past usage → Account.

    Declared as ``/profile`` (not ``/{account}/profile``) so it is never shadowed by ``/{account_number}``.
    """
    ids = [x.strip() for x in batch_ids.split(",") if x.strip()] if batch_ids else None
    prof = fetch_saved_bill_profile(account_number, ids)
    return {"profile": prof}


@router.get("/{account_number}")
def get_bill_usage(
    account_number: str,
    year: str | None = None,
    batch_id: str | None = None,
    uploaded_at: str | None = None,
):
    opts = fetch_uploaded_bill_options()
    opts = opts[opts["account_number"] == account_number]
    if opts.empty:
        raise HTTPException(status_code=404, detail="No uploaded bills for this account.")

    if year:
        opts = opts[opts["bill_year"].astype(str) == str(year)]
    if batch_id and str(batch_id).strip():
        opts = opts[opts["batch_id"].astype(str) == str(batch_id).strip()]
    if uploaded_at:
        ua = pd.to_datetime(uploaded_at)
        opts = opts[pd.to_datetime(opts["uploaded_at"], errors="coerce") == ua]

    if opts.empty:
        raise HTTPException(status_code=404, detail="No rows match year/batch filters.")

    merged = load_usage_merged_for_account(account_number, opts)
    return {"records": df_to_json_safe_records(merged)}
