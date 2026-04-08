from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from backend.routes import anomalies, bills, calculate, export, tariffs, versions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app = FastAPI(title="TroyBanks Audit API")

_cors_raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if _cors_raw == "*":
    _cors_origins: list[str] = ["*"]
else:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if not _cors_origins:
        _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Avoid leaking stack traces to clients; log server-side."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(bills.router, prefix="/api/bills")
app.include_router(calculate.router, prefix="/api/calculate")
app.include_router(anomalies.router, prefix="/api/anomalies")
app.include_router(tariffs.router, prefix="/api")
app.include_router(versions.router, prefix="/api/versions")
app.include_router(export.router, prefix="/api/export")


@app.get("/health")
def health():
    return {"status": "ok"}
