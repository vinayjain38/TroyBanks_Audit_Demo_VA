from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import text

from src.Utils.database import engine
from src.Utils.paths import RIDERS_OUT, SCHEDULES_XLSX
from src.Utils.upload import upload_riders_versioned, upload_tariffs_versioned

router = APIRouter()


@router.post("/tariffs/upload")
async def tariffs_upload(
    file: UploadFile = File(...),
    effective_date: Optional[str] = Query(None),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Expected an Excel file (.xlsx or .xls).")

    ed = effective_date
    if ed:
        try:
            ed = date.fromisoformat(str(ed))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="effective_date must be ISO YYYY-MM-DD.") from exc

    suffix = os.path.splitext(file.filename)[1] or ".xlsx"
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        upload_tariffs_versioned(tmp_path, effective_date=ed)
        SCHEDULES_XLSX.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path, SCHEDULES_XLSX)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM tariff_rates"))
            next_v = result.scalar() or 0
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM tariff_rates WHERE version = :v"), {"v": next_v}).scalar()
        return {"status": "success", "version": int(next_v), "rows_uploaded": int(cnt or 0)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/riders/upload")
async def riders_upload(
    file: UploadFile = File(...),
    effective_date: Optional[str] = Query(None),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Expected an Excel file (.xlsx or .xls).")

    ed = effective_date
    if ed:
        try:
            ed = date.fromisoformat(str(ed))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="effective_date must be ISO YYYY-MM-DD.") from exc

    suffix = os.path.splitext(file.filename)[1] or ".xlsx"
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        upload_riders_versioned(tmp_path, effective_date=ed)
        RIDERS_OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path, RIDERS_OUT)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM rider_rates"))
            next_v = result.scalar() or 0
        return {"status": "success", "version": int(next_v)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
