from __future__ import annotations

import io
from typing import Any, Optional

import pandas as pd
import xlsxwriter
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class ExportBody(BaseModel):
    data: Optional[list[dict[str, Any]]] = None
    sheets: Optional[dict[str, list[dict[str, Any]]]] = None


def _write_sheet(workbook: xlsxwriter.Workbook, sheet_name: str, rows: list[dict]) -> None:
    ws = workbook.add_worksheet(sheet_name[:31] or "Sheet")
    if not rows:
        ws.write(0, 0, "(empty)")
        return
    headers = list(rows[0].keys())
    for c, h in enumerate(headers):
        ws.write(0, c, str(h))
    for r, row in enumerate(rows, start=1):
        for c, h in enumerate(headers):
            v = row.get(h)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                ws.write(r, c, "")
            elif isinstance(v, (pd.Timestamp,)):
                ws.write(r, c, str(v.date()))
            else:
                ws.write(r, c, v)


@router.post("")
def export_excel(body: ExportBody):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    wrote = False
    if body.data:
        _write_sheet(workbook, "Sheet1", body.data)
        wrote = True
    if body.sheets:
        for name, rows in body.sheets.items():
            if not rows:
                continue
            safe = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in str(name))[:31] or "Sheet"
            _write_sheet(workbook, safe, rows)
            wrote = True
    workbook.close()
    if not wrote:
        raise HTTPException(status_code=400, detail="Provide non-empty `data` or `sheets`.")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="export.xlsx"'},
    )
