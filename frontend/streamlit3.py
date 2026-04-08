"""Troy & Banks audit UI: upload bills, analyze usage and rates, exports from analysis tabs."""

from pathlib import Path
import sys
import os
import inspect
from datetime import date, datetime

import requests
import streamlit as st
import pandas as pd
import numpy as np
import re

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- Optional .env (local dev): repo root first, then frontend/ ----
for _env_file in (ROOT.parent / ".env", ROOT / ".env"):
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

os.environ.setdefault("TESSDATA_PREFIX", "/opt/anaconda3/share/tessdata")
os.environ.setdefault("TESSERACT_PATH", "/opt/anaconda3/bin/tesseract")

# Host-run Streamlit: use same host port as API_HOST_PORT in docker-compose (default 8000).
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

try:
    import altair as alt
except ImportError:
    alt = None

def _api_request(method: str, path: str, **kwargs):
    url = f"{BACKEND_URL}{path}"
    try:
        r = requests.request(method, url, timeout=600, **kwargs)
        r.raise_for_status()
        return r
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is it running?")
        raise
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            detail = (getattr(e.response, "text", None) or "").strip()
        st.error(f"API error: {e}" + (f" — {detail}" if detail else ""))
        raise


@st.cache_data(ttl=60)
def _schedule_options(backend_base: str) -> list[str]:
    r = requests.get(f"{backend_base}/api/calculate/schedules", timeout=60)
    r.raise_for_status()
    return list(r.json())


@st.cache_data(ttl=30)
def _calc_sources(backend_base: str):
    r = requests.get(f"{backend_base}/api/calculate/sources", timeout=60)
    r.raise_for_status()
    return r.json()


def _export_bytes_via_api(*, data=None, sheets=None) -> bytes:
    payload = {}
    if data is not None:
        payload["data"] = _records_clean(data)
    if sheets is not None:
        payload["sheets"] = {k: _records_clean(v) for k, v in sheets.items()}
    r = _api_request("post", "/api/export", json=payload)
    return r.content


def _records_clean(rows):
    if rows is None:
        return None
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict(orient="records")
    out = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, np.integer):
                clean[k] = int(v)
            elif isinstance(v, np.floating):
                clean[k] = None if pd.isna(v) else float(v)
            elif isinstance(v, float) and pd.isna(v):
                clean[k] = None
            elif isinstance(v, pd.Timestamp):
                clean[k] = v.isoformat()
            elif isinstance(v, (date, datetime)):
                clean[k] = v.isoformat()
            elif isinstance(v, np.bool_):
                clean[k] = bool(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def _usage_records_for_api(df: pd.DataFrame) -> list[dict]:
    d = df.copy()
    if "bill_period_end" in d.columns:
        d["bill_period_end"] = pd.to_datetime(d["bill_period_end"], errors="coerce")
        d["bill_period_end"] = d["bill_period_end"].dt.strftime("%Y-%m-%d")
    return _records_clean(d.to_dict(orient="records"))


class _ScheduleFuncProxy:
    """Mimics dict of schedule callables; each call hits POST /api/calculate."""

    def keys(self):
        return _schedule_options(BACKEND_URL)

    def __iter__(self):
        return iter(self.keys())

    def get(self, sid, default=None):
        if sid in self.keys():
            return self[sid]
        return default

    def __getitem__(self, sid):
        def _run(df, _riders_df=None):
            body = {
                "schedule_ids": [str(sid)],
                "usage_records": _usage_records_for_api(df),
                "tariff_source": "file",
                "rider_source": "file",
            }
            r = _api_request("post", "/api/calculate", json=body)
            combined = pd.DataFrame(r.json()["records"])
            pref = f"ve{sid}_"
            take = [c for c in combined.columns if str(c).startswith(pref)]
            if not take:
                raise KeyError(f"No schedule columns for VE-{sid} in API response")
            return combined[take]

        return _run


SCHEDULE_FUNCS = _ScheduleFuncProxy()



# ---------------------------------------------------
# Page config & global CSS
# ---------------------------------------------------
st.set_page_config(page_title="Troy & Banks", layout="wide")

st.markdown("""
<style>
/* Dark: black background, white/light text */
[data-testid="stAppViewContainer"] {
    background: #000000 !important;
    color: #f5f5f5;
}
[data-testid="stHeader"], [data-testid="stDecoration"], [data-testid="stToolbar"] {
    background: #000000 !important;
}
section[data-testid="stSidebar"] {
    background-color: #0a0a0a !important;
    border-right: 1px solid #262626 !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] .stMarkdown {
    color: #f0f0f0 !important;
}
/* Sidebar nav: hints above each button */
p.sidebar-nav-lead {
    font-size: 0.76rem !important;
    line-height: 1.6 !important;
    color: #a3a3a3 !important;
    margin: 0.15rem 0 1.05rem 0 !important;
}
p.sidebar-nav-hint {
    font-size: 0.74rem !important;
    line-height: 1.5 !important;
    color: #b8b8b8 !important;
    margin: 0 0 0.5rem 0 !important;
}
p.sidebar-nav-hint strong { color: #f0f0f0 !important; }
p.sidebar-nav-hint span { color: #9ca3af !important; }
div.sidebar-nav-gap {
    height: 1rem;
    min-height: 1rem;
    margin: 0;
    padding: 0;
}
/* Extra top padding avoids first line clipping under the app header */
.block-container {
    padding-top: 2.75rem !important;
    padding-bottom: 2rem;
}
section.main > div {
    padding-top: 0.35rem !important;
}

.main, .main p, .main span, .main label, .stMarkdown, [data-testid="stMarkdownContainer"] p {
    color: #e8e8e8;
}

/* Bordered blocks (billing + TOTAL): avoid clipping the footer dataframe */
[data-testid="stVerticalBlockBorderWrapper"] {
    overflow: visible;
}

/* Hero */
.hero {
    position: relative;
    overflow: hidden;
    background: #0a0a0a;
    border: 1px solid #333333;
    border-radius: 12px;
    padding: 2.4rem 2.8rem;
    margin-bottom: 2rem;
    display: flex;
    align-items: center;
    gap: 2rem;
}
.hero-body { z-index: 1; flex: 1; min-width: 0; }
.hero-title {
    font-size: 1.75rem; font-weight: 800; margin: 0; line-height: 1.2;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff;
    background: none;
}
.hero-sub { font-size: 0.82rem; color: #b0b0b0; margin: 0.3rem 0 0 0; letter-spacing: 0.04em; }
.hero-divider {
    height: 1px;
    background: #333333;
    margin: 0.7rem 0 0.55rem;
}
.hero-meta {
    font-size: 0.74rem; color: #a3a3a3; letter-spacing: 0.04em;
    font-weight: 500; line-height: 1.6;
}
.hero-meta strong { color: #e5e5e5; font-weight: 600; }
.hero-meta .sep { color: #525252; margin: 0 0.45rem; }

/* Upload */
[data-testid="stFileUploader"] { margin: 0.5rem 0 0.4rem; }
[data-testid="stFileUploaderDropzone"] {
    background: #0a0a0a !important;
    border: 2px dashed #404040 !important;
    border-radius: 16px !important;
    padding: 2.6rem 2rem 2.2rem !important;
    min-height: 240px;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: border-color 0.2s ease;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: #737373 !important; }
[data-testid="stFileUploaderDropzone"] svg { color: #e5e5e5 !important; width: 2.2rem !important; height: 2.2rem !important; opacity: 0.9; }
[data-testid="stFileUploaderDropzoneInstructions"] span:first-child {
    color: #ffffff !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] small {
    color: #a3a3a3 !important; font-size: 0.8rem !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: #ffffff !important;
    color: #000000 !important;
    border: 1px solid #e5e5e5 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    margin-top: 0.4rem;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: #f0f0f0 !important;
}

.results-nav {
    display: flex; align-items: center; justify-content: space-between;
    background: #0a0a0a;
    border: 1px solid #333333; border-radius: 12px;
    padding: 0.9rem 1.4rem; margin-bottom: 1.2rem;
}
.results-nav-left { display: flex; align-items: center; gap: 0.8rem; }
.results-nav-mark {
    width: 8px; height: 8px; border-radius: 50%; background: #ffffff; flex-shrink: 0;
}
.results-nav-title {
    font-size: 1rem; font-weight: 800; letter-spacing: 0.06em;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff;
}
.results-nav-file { font-size: 0.75rem; color: #a3a3a3; margin-top: 0.1rem; }

.kpi-row { display: flex; gap: 1rem; margin: 1rem 0; flex-wrap: wrap; }
/* Uniform KPI tiles: equal width in row, fixed height, aligned content */
.kpi-row.kpi-row-uniform {
    flex-wrap: nowrap !important;
    align-items: stretch;
    gap: 1rem;
}
.kpi-row.kpi-row-uniform .kpi-card {
    flex: 1 1 0;
    min-width: 0;
    box-sizing: border-box;
    width: 0;
    height: 10rem;
    min-height: 10rem;
    max-height: 10rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 1rem 1.15rem;
    overflow: hidden;
}
.kpi-row.kpi-row-uniform .kpi-label {
    line-height: 1.2;
    max-height: 2.4em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.kpi-row.kpi-row-uniform .kpi-value {
    word-break: break-word;
    line-height: 1.2;
}
.kpi-row.kpi-row-uniform .kpi-sub {
    line-height: 1.2;
    max-height: 2.4em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
/* Rate / Schedule compare: one row, equal-width tiles (no wrap — avoids stretched last row) */
.kpi-row.compare-kpi-band {
    flex-wrap: nowrap !important;
    align-items: stretch;
    gap: 1rem;
    margin: 0.25rem 0 1rem 0 !important;
}
.kpi-row.compare-kpi-band .kpi-card {
    flex: 1 1 0;
    min-width: 0;
    box-sizing: border-box;
    width: 0;
    height: 10rem;
    min-height: 10rem;
    max-height: 10rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 1rem 1.15rem;
    overflow: hidden;
}
.kpi-row.compare-kpi-band .kpi-label {
    line-height: 1.2;
    max-height: 2.4em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.kpi-row.compare-kpi-band .kpi-value {
    word-break: break-word;
    line-height: 1.2;
}
.kpi-row.compare-kpi-band .kpi-sub {
    line-height: 1.2;
    max-height: 2.4em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.kpi-card {
    background: #0a0a0a;
    border: 1px solid #333333;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    flex: 1; min-width: 160px;
}
.kpi-label { font-size: 0.75rem; color: #a3a3a3; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.4rem; }
.kpi-value { font-size: 1.6rem; font-weight: 700; color: #ffffff; }
.kpi-sub { font-size: 0.78rem; color: #a3a3a3; margin-top: 0.2rem; }
.kpi-positive { color: #86efac; }
.kpi-negative { color: #fca5a5; }

.section-title {
    font-size: 1rem; font-weight: 600; color: #e5e5e5;
    text-transform: uppercase; letter-spacing: 0.1em;
    border-bottom: 1px solid #333333;
    padding-bottom: 0.4rem; margin: 1.2rem 0 0.8rem 0;
}

.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
.info-item {
    background: #0a0a0a; border: 1px solid #333333;
    border-radius: 8px; padding: 0.7rem 1rem;
}
.info-item-label { font-size: 0.72rem; color: #a3a3a3; text-transform: uppercase; letter-spacing: 0.06em; }
.info-item-value { font-size: 0.95rem; color: #f5f5f5; font-weight: 500; margin-top: 0.15rem; word-break: break-word; }

[data-testid="stTabs"] [role="tablist"] {
    gap: 0.2rem;
    background: #0a0a0a;
    border: 1px solid #333333;
    border-radius: 12px;
    padding: 0.25rem;
    margin-bottom: 0.8rem;
    box-shadow: none !important;
}
/* Tabs: stay on dark surfaces; selected = elevated gray, never white (avoids Base Web text/focus clash) */
[data-testid="stTabs"] [role="tab"],
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-size: 0.86rem;
    font-weight: 600;
    color: #a3a3a3 !important;
    background: transparent !important;
    padding: 0.52rem 0.95rem;
    border-radius: 8px;
    border: 1px solid transparent !important;
    outline: none !important;
    box-shadow: none !important;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stTabs"] [role="tab"] *,
[data-testid="stTabs"] button[data-baseweb="tab"] * {
    color: inherit !important;
    -webkit-text-fill-color: inherit !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"],
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: #ffffff !important;
    background: #262626 !important;
    border-color: #525252 !important;
    -webkit-text-fill-color: #ffffff !important;
    box-shadow: none !important;
}
[data-testid="stTabs"] [role="tab"]:hover:not([aria-selected="true"]),
[data-testid="stTabs"] button[data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    color: #ffffff !important;
    background: #171717 !important;
}
[data-testid="stTabs"] [role="tab"]:focus,
[data-testid="stTabs"] [role="tab"]:focus-visible,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
    outline: none !important;
}
[data-testid="stTabs"] [role="tab"]:focus-visible,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
    box-shadow: 0 0 0 2px #737373 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]:focus-visible,
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"]:focus-visible {
    background: #2e2e2e !important;
    color: #ffffff !important;
    box-shadow: 0 0 0 2px #a3a3a3 !important;
}
/* Base Web sliding highlight — neutral (removes default red accent flash) */
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background: #d4d4d4 !important;
}

[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label { color: #d4d4d4 !important; font-size: 0.8rem; }
[data-baseweb="select"] > div {
    background-color: #0a0a0a !important;
    border-color: #404040 !important;
}
[data-baseweb="select"] * {
    color: #f5f5f5 !important;
}
[data-testid="stTextInput"] input {
    background-color: #0a0a0a !important;
    color: #f5f5f5 !important;
    border: 1px solid #404040 !important;
}
[data-testid="stDateInput"] input {
    background-color: #0a0a0a !important;
    color: #f5f5f5 !important;
    border: 1px solid #404040 !important;
}
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid #333333; }

[data-testid="stDownloadButton"] > button {
    background: #262626 !important;
    color: #ffffff !important;
    border: 1px solid #525252 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
[data-testid="stDownloadButton"] > button * {
    color: #ffffff !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #333333 !important;
    border-color: #737373 !important;
}
[data-testid="stDownloadButton"] > button:hover * {
    color: #ffffff !important;
}

[data-testid="stButton"] > button[kind="secondary"] {
    background: transparent !important;
    color: #e5e5e5 !important;
    border: 1px solid #404040 !important;
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    padding: 0.35rem 0.9rem !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover {
    border-color: #737373 !important;
    color: #ffffff !important;
}

/* Primary: force dark label on light fill (Base Web can leave white text on pale gray) */
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]) {
    background: #f0f0f0 !important;
    color: #0a0a0a !important;
    border: 1px solid #d4d4d4 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]) * {
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):hover {
    background: #ffffff !important;
    border-color: #e5e5e5 !important;
    color: #000000 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):hover * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):focus-visible {
    box-shadow: 0 0 0 2px #737373 !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled,
[data-testid="stButton"] > button[kind="primary"][disabled],
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] {
    background: #404040 !important;
    color: #f5f5f5 !important;
    border-color: #525252 !important;
    opacity: 0.9 !important;
    -webkit-text-fill-color: #f5f5f5 !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled *,
[data-testid="stButton"] > button[kind="primary"][disabled] *,
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] * {
    color: #f5f5f5 !important;
    -webkit-text-fill-color: #f5f5f5 !important;
}

hr { border-color: #333333 !important; }

.form-panel {
    background: #0a0a0a;
    border: 1px solid #333333;
    border-radius: 12px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.8rem;
    color: #e5e5e5;
}

.premium-strip {
    border: 1px solid #404040;
    border-radius: 12px;
    background: #0a0a0a;
    padding: 0.85rem 1rem 0.8rem;
    color: #d4d4d4;
    font-size: 0.82rem;
    margin: 0.5rem 0 1rem;
    line-height: 1.55;
    letter-spacing: 0.02em;
    overflow: visible;
}

[data-testid="stMetric"] label { color: #a3a3a3 !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #ffffff !important; }

[data-testid="stExpander"] summary { color: #e5e5e5 !important; }

[data-testid="stAlert"] { background-color: #141414 !important; color: #f5f5f5 !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { color: #f5f5f5 !important; }
[data-testid="stAlert"] a { color: #93c5fd !important; }

/* Captions, help text, widget labels */
[data-testid="stCaption"],
[data-testid="stWidgetLabel"] label,
label[data-testid="stWidgetLabel"] {
    color: #b3b3b3 !important;
}
[data-testid="stMarkdownContainer"] small { color: #a3a3a3 !important; }

/* Sidebar radio (theme toggle, etc.) */
[data-testid="stSidebar"] [data-baseweb="radio"] label,
[data-testid="stSidebar"] [data-baseweb="radio"] span {
    color: #f0f0f0 !important;
}

[data-testid="stNumberInput"] label { color: #d4d4d4 !important; }
[data-testid="stNumberInput"] input {
    background-color: #0a0a0a !important;
    color: #f5f5f5 !important;
    border: 1px solid #404040 !important;
}

[data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] span { color: #e8e8e8 !important; }
[data-testid="stToggle"] label { color: #e8e8e8 !important; }

/* Tab panel content */
[data-testid="stTabs"] [role="tabpanel"],
[data-testid="stTabs"] [role="tabpanel"] p,
[data-testid="stTabs"] [role="tabpanel"] label {
    color: #e8e8e8 !important;
}

[data-testid="stButton"] > button[kind="secondary"] * {
    color: inherit !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover * {
    color: #ffffff !important;
}

.main a, [data-testid="stMarkdownContainer"] a { color: #93c5fd !important; }

[data-testid="stExpander"] [data-testid="stVerticalBlock"] p,
[data-testid="stExpander"] [data-testid="stVerticalBlock"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #e8e8e8 !important;
}

/* Select / multiselect dropdown surface */
[data-baseweb="popover"] {
    background-color: #141414 !important;
    border: 1px solid #404040 !important;
}
[data-baseweb="popover"] li,
[data-baseweb="popover"] [role="option"] {
    color: #f5f5f5 !important;
    background-color: #141414 !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] [role="option"]:hover {
    background-color: #262626 !important;
}

/* Multiselect tags — red chips (classic Past usage look) */
[data-testid="stMultiSelect"] [data-baseweb="tag"] {
    background-color: #dc2626 !important;
    color: #ffffff !important;
    border-color: #b91c1c !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] span,
[data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
    color: #ffffff !important;
}

</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------
def _parse_money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip(),
        errors="coerce",
    ).fillna(0.0)


# ---------------------------------------------------
# Shared helpers
# ---------------------------------------------------
_ST_DATAFRAME_SIG = inspect.signature(st.dataframe)
_DATAFRAME_SUPPORTS_KEY = "key" in _ST_DATAFRAME_SIG.parameters
try:
    _CONTAINER_SUPPORTS_BORDER = "border" in inspect.signature(st.container).parameters
except (TypeError, ValueError):
    _CONTAINER_SUPPORTS_BORDER = False


def _billing_block():
    """One bordered shell so billing + TOTAL read as a single block (Streamlit ≥1.33)."""
    if _CONTAINER_SUPPORTS_BORDER:
        return st.container(border=True)
    return st.container()


def _st_dataframe(df: pd.DataFrame, **kwargs) -> None:
    """``st.dataframe`` wrapper: older Streamlit builds omit ``key`` on dataframes."""
    if not _DATAFRAME_SUPPORTS_KEY:
        kwargs.pop("key", None)
    st.dataframe(df, **kwargs)


def add_total(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = df.select_dtypes(include=["number"]).columns
    totals = df[numeric_cols].sum()
    row = {col: None for col in df.columns}
    for col in numeric_cols:
        row[col] = totals[col]
    row["bill_period_end"] = "TOTAL"
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def split_billing_rows_and_total(df: pd.DataFrame, period_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detail rows vs rows whose period column equals TOTAL (case-insensitive)."""
    if df is None or df.empty or period_col not in df.columns:
        return pd.DataFrame(), pd.DataFrame()
    d = df.copy()
    tot_mask = d[period_col].astype(str).str.upper() == "TOTAL"
    total_part = d.loc[tot_mask].reset_index(drop=True)
    detail = d.loc[~tot_mask].reset_index(drop=True)
    return detail, total_part


def compute_total_row_from_detail(detail: pd.DataFrame, period_col: str) -> pd.DataFrame:
    """One TOTAL row: sum of numeric columns (same idea as add_total)."""
    if detail.empty:
        return pd.DataFrame()
    numeric_cols = detail.select_dtypes(include=["number"]).columns
    row = {c: None for c in detail.columns}
    for col in numeric_cols:
        row[col] = float(pd.to_numeric(detail[col], errors="coerce").sum())
    row[period_col] = "TOTAL"
    if "Rate" in row:
        row["Rate"] = "—"
    return pd.DataFrame([row])


def render_dataframe_with_fixed_total(
    display_df: pd.DataFrame,
    *,
    period_col: str,
    column_config: dict,
    key_prefix: str,
    detail_height: int = 460,
    total_height: int = 0,
) -> None:
    """Billing rows in ``st.dataframe`` (native column sorting); **TOTAL** in a second table below (fixed).

    ``total_height``: if 0, the TOTAL table is auto-sized (recommended so the header + row are not clipped).
    If > 0, sets that pixel height (use only when you need a cap).
    """
    detail, total = split_billing_rows_and_total(display_df, period_col)
    if total.empty and not detail.empty:
        total = compute_total_row_from_detail(detail, period_col)
    if detail.empty and total.empty:
        _st_dataframe(display_df, width="stretch", hide_index=True, column_config=column_config)
        return
    # Two dataframes are required so TOTAL never joins the sortable grid; one bordered block keeps them visually together.
    with _billing_block():
        _st_dataframe(
            detail.reset_index(drop=True),
            width="stretch",
            height=detail_height,
            hide_index=True,
            column_config=column_config,
            key=f"{key_prefix}_detail",
        )
        st.markdown(
            '<div aria-hidden="true" style="height:1px;background:#333333;margin:0.15rem 0 0.25rem 0;"></div>',
            unsafe_allow_html=True,
        )
        _total_kw: dict = {
            "width": "stretch",
            "hide_index": True,
            "column_config": column_config,
            "key": f"{key_prefix}_total",
        }
        if total_height > 0:
            _total_kw["height"] = total_height
        _st_dataframe(total.reset_index(drop=True), **_total_kw)
    st.caption(
        "Sort **billing rows** with column headers (same as a normal table). **TOTAL** stays at the bottom of the box and does not move when you sort."
    )


def export_excel(df: pd.DataFrame) -> bytes:
    if df is None or getattr(df, "empty", True):
        return _export_bytes_via_api(data=[{"info": "No rows to export."}])
    return _export_bytes_via_api(data=df)


def export_excel_multi_sheet(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Write multiple dataframes to one .xlsx (sheet names truncated/sanitized for Excel). Skips empty frames."""
    out: dict[str, pd.DataFrame] = {}
    used: set[str] = set()
    for raw_name, df in sheets.items():
        if df is None or getattr(df, "empty", True):
            continue
        base = re.sub(r'[\[\]:*?/\\]', "_", str(raw_name)).strip() or "Sheet"
        sn = base[:31]
        n = 1
        while sn in used:
            suffix = f"_{n}"
            sn = (base[: 31 - len(suffix)] + suffix)[:31]
            n += 1
        used.add(sn)
        out[sn] = df
    if not out:
        return export_excel(pd.DataFrame({"info": ["No non-empty tables to export."]}))
    return _export_bytes_via_api(sheets=out)


def reorder_first(df: pd.DataFrame, col: str = "bill_period_end") -> pd.DataFrame:
    cols = df.columns.tolist()
    if col in cols:
        cols.remove(col)
        cols = [col] + cols
    return df[cols]


def monthly_calculated_view_columns(df: pd.DataFrame) -> list:
    """bill_period_end, optional bill_month, usage_kwh, charges, plus VE calculated / savings only."""
    out = []
    if "bill_period_end" in df.columns:
        out.append("bill_period_end")
    if "bill_month" in df.columns:
        out.append("bill_month")
    for c in ("usage_kwh", "charges"):
        if c in df.columns and c not in out:
            out.append(c)
    for c in df.columns:
        if c in out:
            continue
        sl = str(c).lower()
        if "case_type" in sl:
            continue
        if "_calculated_amount" in sl or "_savings" in sl or "_saving" in sl:
            out.append(c)
            continue
        if "calculated" in sl and "ve" in sl:
            out.append(c)
    seen = set()
    ordered = []
    for c in out:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def monthly_calculated_view_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = monthly_calculated_view_columns(df)
    if not cols:
        return df.copy()
    return df[[c for c in cols if c in df.columns]].copy()


def monthly_view_column_config(df: pd.DataFrame) -> dict:
    cfg = {}
    for c in df.columns:
        sl = str(c).lower()
        # Period columns first (avoid matching substrings like "kwh" in unrelated names).
        if c == "bill_period_end" or sl == "bill_month":
            cfg[c] = st.column_config.TextColumn(str(c))
        elif sl == "charges" or "calculated" in sl or "saving" in sl or "$" in str(c):
            cfg[c] = st.column_config.NumberColumn(str(c), format="$%.2f")
        elif "usage" in sl or "kwh" in sl:
            cfg[c] = st.column_config.NumberColumn(str(c), format="%.0f")
        elif "gap" in sl or sl.startswith("gap_"):
            cfg[c] = st.column_config.NumberColumn(str(c), format="$%.2f")
        elif "pct" in sl or "variance" in sl:
            cfg[c] = st.column_config.NumberColumn(str(c), format="%.1f")
        elif pd.api.types.is_numeric_dtype(df[c]):
            cfg[c] = st.column_config.NumberColumn(str(c))
        else:
            cfg[c] = st.column_config.TextColumn(str(c))
    return cfg


def account_billing_column_config(df: pd.DataFrame) -> dict:
    """Column config for Account → All Billing Records."""
    cfg = {}
    for c in df.columns:
        if c == "Bill Period":
            cfg[c] = st.column_config.TextColumn(c)
        elif c == "Rate":
            cfg[c] = st.column_config.TextColumn(c)
        elif c == "Usage (kWh)":
            cfg[c] = st.column_config.NumberColumn(c, format="%.0f")
        elif c == "Demand (kW)":
            cfg[c] = st.column_config.NumberColumn(c, format="%.2f")
        elif c == "Charges ($)":
            cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
        elif pd.api.types.is_numeric_dtype(df[c]):
            cfg[c] = st.column_config.NumberColumn(c)
        else:
            cfg[c] = st.column_config.TextColumn(c)
    return cfg


def merged_comparison_column_config(df: pd.DataFrame, decimals: int = 6) -> dict:
    """Rate compare detailed table: riders + base columns."""
    cfg = {}
    for c in df.columns:
        sl = str(c).lower()
        if re.match(r"^ve\d+_rider_charge$", c):
            cfg[c] = st.column_config.NumberColumn(c, format=f"$%.{decimals}f")
        elif c == "bill_period_end":
            cfg[c] = st.column_config.TextColumn(c)
        elif c == "charges" or "calculated" in sl or "saving" in sl or "$" in str(c):
            cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
        elif c == "usage_kwh" or ("usage" in sl and "kwh" in sl):
            cfg[c] = st.column_config.NumberColumn(c, format="%.0f")
        elif c == "demand_kw" or ("demand" in sl and "kw" in sl):
            cfg[c] = st.column_config.NumberColumn(c, format="%.2f")
        elif c == "current_rate":
            cfg[c] = st.column_config.TextColumn(c)
        elif pd.api.types.is_numeric_dtype(df[c]):
            cfg[c] = st.column_config.NumberColumn(c)
        else:
            cfg[c] = st.column_config.TextColumn(c)
    return cfg


def monthly_actual_vs_calculated_gaps(merged: pd.DataFrame, calc_col: str) -> pd.DataFrame:
    """Per bill row: actual charges, model calculated, dollar gap and % vs calculated (excludes TOTAL)."""
    if merged is None or merged.empty or calc_col not in merged.columns or "charges" not in merged.columns:
        return pd.DataFrame()
    d = merged.copy()
    mask = d["bill_period_end"].astype(str).str.upper() != "TOTAL"
    d = d.loc[mask]
    ch = pd.to_numeric(d["charges"], errors="coerce")
    calc = pd.to_numeric(d[calc_col], errors="coerce")
    gap = ch - calc
    pct = np.where(calc.abs() > 1e-6, (gap / calc) * 100.0, np.nan)
    out = pd.DataFrame(
        {
            "bill_period_end": d["bill_period_end"],
            "actual_charges": ch,
            "calculated": calc,
            "gap_actual_minus_calculated": gap,
            "gap_pct_of_calculated": pct,
        }
    )
    return out.reset_index(drop=True)


def schedule_compare_gap_table(comp: pd.DataFrame, schedule_ids: list) -> pd.DataFrame:
    """One row per bill: charges minus each selected schedule’s calculated amount."""
    if comp is None or comp.empty or "charges" not in comp.columns:
        return pd.DataFrame()
    base_cols = [c for c in ("bill_period_end", "usage_kwh", "charges") if c in comp.columns]
    out = comp[base_cols].copy()
    ch = pd.to_numeric(out["charges"], errors="coerce")
    for sid in schedule_ids:
        col = f"VE-{sid} Calculated ($)"
        if col in comp.columns:
            calc = pd.to_numeric(comp[col], errors="coerce")
            out[f"gap_vs_VE_{sid} ($)"] = ch - calc
    return out.reset_index(drop=True)


def anomaly_params_from_session() -> dict:
    return {
        "pct_spike_limit": float(st.session_state.get("anom_yoy_pct", 0.5)),
        "abs_spike_limit": float(st.session_state.get("anom_abs_daily", 5.0)),
        "billing_median_multiplier": float(st.session_state.get("anom_bill_mult", 2.5)),
        "billing_min_delta_cpk": float(st.session_state.get("anom_bill_delta_cpk", 0.05)),
        "billing_min_kwh": float(st.session_state.get("anom_bill_min_kwh", 30.0)),
        "charge_median_multiplier": float(st.session_state.get("anom_charge_mult", 2.5)),
        "charge_min_usd": float(st.session_state.get("anom_charge_min_usd", 100.0)),
    }


def render_anomaly_detection_settings_expander() -> None:
    with st.expander("Anomaly detection settings", expanded=False):
        st.caption(
            "Applies to every Anomalies table in Analysis and on **Past usage bills**. "
            "Other automated jobs may still use their own defaults."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "YoY usage spike (fraction above same-month median daily kWh)",
                0.1,
                1.0,
                value=float(st.session_state.get("anom_yoy_pct", 0.5)),
                step=0.05,
                key="anom_yoy_pct",
                help="e.g. 0.50 = 50% higher than historical median for that month",
            )
            st.number_input(
                "Min. absolute daily kWh increase (usage spike)",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.get("anom_abs_daily", 5.0)),
                step=0.5,
                key="anom_abs_daily",
            )
            st.number_input(
                "Billing $/kWh: multiplier vs account median",
                min_value=1.0,
                max_value=10.0,
                value=float(st.session_state.get("anom_bill_mult", 2.5)),
                step=0.1,
                key="anom_bill_mult",
            )
            st.number_input(
                "Billing $/kWh: min. $/kWh above median",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("anom_bill_delta_cpk", 0.05)),
                step=0.01,
                format="%.2f",
                key="anom_bill_delta_cpk",
            )
        with c2:
            st.number_input(
                "Billing $/kWh: minimum usage (kWh) to evaluate",
                min_value=0.0,
                max_value=5000.0,
                value=float(st.session_state.get("anom_bill_min_kwh", 30.0)),
                step=10.0,
                key="anom_bill_min_kwh",
            )
            st.number_input(
                "Charge spike: multiplier vs median bill ($)",
                min_value=1.0,
                max_value=10.0,
                value=float(st.session_state.get("anom_charge_mult", 2.5)),
                step=0.1,
                key="anom_charge_mult",
            )
            st.number_input(
                "Charge spike: minimum bill amount ($)",
                min_value=0.0,
                max_value=5000.0,
                value=float(st.session_state.get("anom_charge_min_usd", 100.0)),
                step=25.0,
                key="anom_charge_min_usd",
            )


def _strip_total_and_parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Drop TOTAL rows and coerce bill_period_end for anomaly logic."""
    if df is None or df.empty or "bill_period_end" not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    mask = d["bill_period_end"].astype(str).str.upper() != "TOTAL"
    d = d.loc[mask]
    d["bill_period_end"] = pd.to_datetime(d["bill_period_end"], errors="coerce")
    return d.dropna(subset=["bill_period_end"])


def build_anomalies_export_table(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Same grid as the Anomalies table / Excel download (for multi-sheet workbooks)."""
    pe = _strip_total_and_parse_dates(usage_full_history)
    if pe.empty or "contract_account" not in pe.columns:
        return pd.DataFrame()
    acct = str(pe["contract_account"].dropna().iloc[0])
    p = anomaly_params_from_session()
    params = {
        "pct_spike_limit": p["pct_spike_limit"],
        "abs_spike_limit": p["abs_spike_limit"],
        "billing_median_multiplier": p["billing_median_multiplier"],
        "billing_min_delta_cpk": p["billing_min_delta_cpk"],
        "billing_min_kwh": p["billing_min_kwh"],
        "charge_median_multiplier": p["charge_median_multiplier"],
        "charge_min_usd": p["charge_min_usd"],
    }
    if view_period_df is not None and not view_period_df.empty:
        vp = _strip_total_and_parse_dates(view_period_df)
        if not vp.empty:
            params["view_start"] = vp["bill_period_end"].min().date().isoformat()
            params["view_end"] = vp["bill_period_end"].max().date().isoformat()
    r = _api_request("get", f"/api/anomalies/{acct}", params=params)
    records = r.json().get("records") or []
    if not records:
        return pd.DataFrame()
    disp = pd.DataFrame(records)
    if "bill_period_end" in disp.columns:
        disp["bill_period_end"] = pd.to_datetime(disp["bill_period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    return disp


def render_anomalies_section(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
    title: str = "Anomalies (usage YoY and billing)",
    key_suffix: str = "",
) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    st.caption(
        "Flags unusual year-over-year usage, new usage patterns, atypical $/kWh, or a bill much larger than your norm. "
        "Tune rules in **Anomaly detection settings** above."
    )
    try:
        disp = build_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
    except Exception as exc:
        st.warning(f"Could not compute anomalies: {exc}")
        return

    if disp.empty:
        st.info(
            "No anomalies in this view for the current rules. "
            "Try widening thresholds in **Anomaly detection settings**, or pick a different period."
        )
        return
    cfg = {
        "charges": st.column_config.NumberColumn("charges", format="$%.2f"),
        "usage_kwh": st.column_config.NumberColumn("usage_kwh", format="%.0f"),
        "$/kWh": st.column_config.NumberColumn("$/kWh", format="%.4f"),
        "usage_spike": st.column_config.CheckboxColumn("usage spike"),
        "new_activation": st.column_config.CheckboxColumn("new activation"),
        "billing_outlier": st.column_config.CheckboxColumn("billing $/kWh"),
        "charge_spike": st.column_config.CheckboxColumn("charge vs median"),
        "notes": st.column_config.TextColumn("notes", width="large"),
    }
    st.dataframe(disp, width="stretch", hide_index=True, column_config=cfg)
    safe = re.sub(r"[^\w]+", "_", key_suffix).strip("_")[:40] or "anomalies"
    st.download_button(
        "Download anomalies (Excel)",
        data=export_excel(disp),
        file_name=f"troy_banks_anomalies_{safe}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_anom_{safe}"[:120],
    )


def rider_col_config(df: pd.DataFrame, decimals: int = 6) -> dict:
    return {
        c: st.column_config.NumberColumn(c, format=f"$%.{decimals}f")
        for c in df.columns if re.match(r"^ve\d+_rider_charge$", c)
    }


def kpi_card(label: str, value: str, sub: str = "", cls: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    val_cls = f"kpi-value {cls}".strip()
    return (f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="{val_cls}">{value}</div>'
            f'{sub_html}'
            f'</div>')


def info_item(label: str, value: str) -> str:
    return (f'<div class="info-item">'
            f'<div class="info-item-label">{label}</div>'
            f'<div class="info-item-value">{value or "—"}</div>'
            f'</div>')


def render_usage_results_header(
    *,
    source_label: str,
    customer_name: str,
    contract_id: str,
    back_button_key: str,
) -> None:
    """Same top bar as Upload → Results: TROY & BANKS, source · customer · contract, Back to upload."""
    nav_left, nav_right = st.columns([4, 1])
    with nav_left:
        st.markdown(
            f'<div class="results-nav">'
            f'<div class="results-nav-left">'
            f'<span class="results-nav-mark" aria-hidden="true"></span>'
            f'<div>'
            f'<div class="results-nav-title">TROY &amp; BANKS</div>'
            f'<div class="results-nav-file">{source_label} &nbsp;·&nbsp; {customer_name} &nbsp;·&nbsp; {contract_id}</div>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("Back to upload", type="secondary", key=back_button_key):
            st.session_state["page"] = "upload"
            st.session_state["usage_df"] = None
            st.session_state["profile"] = {}
            st.session_state["file_id"] = None
            st.session_state["usage_bills_pdf_batch_key"] = None
            st.rerun()


def render_account_usage_charges_section(
    usage_df: pd.DataFrame,
    *,
    profile: dict | None,
    widget_key_prefix: str = "",
    show_profile_section: bool = True,
) -> None:
    """Profile (optional), Usage & Charges charts/table, anomalies — same as Upload → Results → Account tab."""
    usage_df = usage_df.copy()
    usage_df["bill_period_end"] = pd.to_datetime(usage_df["bill_period_end"], errors="coerce")
    usage_df = usage_df.dropna(subset=["bill_period_end"])
    if usage_df.empty:
        st.warning("No valid billing rows in this view.")
        return

    if show_profile_section:
        if profile:
            st.markdown('<div class="section-title">Profile Details (from PDF)</div>', unsafe_allow_html=True)
            profile_fields = [
                "ACCOUNT NO.", "Phone Number", "Mailing Address",
                "Service Address", "Customer Class", "Turn On Date",
                "District Office", "Meter Number(s)", "Current Rate",
                "Voltage", "Delivery Phase", "Billing Status", "Key Account Manager",
            ]
            items = [
                info_item(lbl, str(profile[lbl]))
                for lbl in profile_fields
                if lbl in profile and str(profile[lbl]).lower() not in ("nan", "none", "")
            ]
            if items:
                st.markdown('<div class="info-grid">' + "".join(items) + "</div>", unsafe_allow_html=True)
        else:
            st.info("No profile data found in the PDF.")

        st.markdown("<hr>", unsafe_allow_html=True)

    _ktoggle = f"{widget_key_prefix}account_usage_table_toggle"

    _utitle, _umode = st.columns([0.62, 0.38])
    with _utitle:
        st.markdown('<div class="section-title">Usage & Charges Over Time</div>', unsafe_allow_html=True)
    with _umode:
        if hasattr(st, "toggle"):
            _table_only = st.toggle(
                "Table",
                value=False,
                key=_ktoggle,
                help="Off: monthly charts. On: billing records table.",
            )
        else:
            _table_only = st.checkbox(
                "Table",
                value=False,
                key=_ktoggle,
                help="Off: monthly charts. On: billing records table.",
            )
    st.caption(
        "Every calendar month from your first bill through your last bill is shown. "
        "Months with no bill are zero. Multiple bills in one month are summed."
    )
    _raw = usage_df[["bill_period_end", "usage_kwh", "charges"]].copy()
    _raw["bill_period_end"] = pd.to_datetime(_raw["bill_period_end"], errors="coerce")
    _raw = _raw.dropna(subset=["bill_period_end"])
    if _raw.empty:
        chart_df = pd.DataFrame(columns=["bill_period_end", "Usage (kWh)", "Charges ($)"])
    else:
        _raw["_m"] = _raw["bill_period_end"].dt.to_period("M")
        monthly = _raw.groupby("_m", as_index=True)[["usage_kwh", "charges"]].sum()
        _full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
        monthly = monthly.reindex(_full, fill_value=0.0)
        monthly = monthly.copy()
        monthly["bill_period_end"] = monthly.index.to_timestamp()
        monthly = monthly.reset_index(drop=True)
        chart_df = monthly.rename(
            columns={"usage_kwh": "Usage (kWh)", "charges": "Charges ($)"}
        )

    disp_cols = [c for c in ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"] if c in usage_df.columns]
    disp = usage_df[disp_cols].copy()
    disp["bill_period_end"] = disp["bill_period_end"].dt.strftime("%Y-%m-%d")
    disp = disp.rename(columns={
        "bill_period_end": "Bill Period", "current_rate": "Rate",
        "usage_kwh": "Usage (kWh)", "demand_kw": "Demand (kW)", "charges": "Charges ($)",
    })

    _show_chart = not _table_only
    _show_table = _table_only

    if _show_chart:
        if chart_df.empty:
            st.info("No billing dates to chart.")
        else:
            _n_months = len(chart_df)
            c_left, c_right = st.columns(2, gap="medium")
            if alt is not None:
                _axis_x = alt.X(
                    "bill_period_end:T",
                    axis=alt.Axis(
                        format="%b %Y",
                        labelAngle=-45 if _n_months <= 24 else -65,
                        title=None,
                        labelOverlap=False,
                        tickCount=_n_months,
                    ),
                )

                def _usage_charges_theme(chart: alt.Chart) -> alt.Chart:
                    return (
                        chart.properties(height=320 if _n_months > 18 else 280)
                        .configure(background="#0a0a0a")
                        .configure_view(stroke="#333333")
                        .configure_axis(
                            labelColor="#a3a3a3",
                            titleColor="#e5e5e5",
                            gridColor="#333333",
                            domainColor="#333333",
                        )
                    )

                with c_left:
                    st.markdown("**Usage (kWh) by month**")
                    ch_u = _usage_charges_theme(
                        alt.Chart(chart_df)
                        .mark_area(line=True, color="#c4c4c4", interpolate="monotone")
                        .encode(
                            x=_axis_x,
                            y=alt.Y("Usage (kWh):Q", title="kWh"),
                        )
                    )
                    st.altair_chart(ch_u, use_container_width=True)
                with c_right:
                    st.markdown("**Charges ($) by month**")
                    ch_c = _usage_charges_theme(
                        alt.Chart(chart_df)
                        .mark_area(line=True, color="#9ca3af", interpolate="monotone")
                        .encode(
                            x=_axis_x,
                            y=alt.Y("Charges ($):Q", title="$"),
                        )
                    )
                    st.altair_chart(ch_c, use_container_width=True)
            else:
                with c_left:
                    st.markdown("**Usage (kWh) by month**")
                    st.area_chart(chart_df.set_index("bill_period_end")["Usage (kWh)"], color="#c4c4c4")
                with c_right:
                    st.markdown("**Charges ($) by month**")
                    st.area_chart(chart_df.set_index("bill_period_end")["Charges ($)"], color="#9ca3af")
                st.caption("Install **altair** for month names on the horizontal axis (`pip install altair`).")

    if _show_table:
        st.markdown('<div class="section-title">All Billing Records</div>', unsafe_allow_html=True)
        if disp.empty:
            st.info("No billing records.")
        else:
            acct_full = pd.concat(
                [disp.reset_index(drop=True), compute_total_row_from_detail(disp, "Bill Period")],
                ignore_index=True,
            )
            acct_cfg = account_billing_column_config(disp)
            render_dataframe_with_fixed_total(
                acct_full,
                period_col="Bill Period",
                column_config=acct_cfg,
                key_prefix=f"{widget_key_prefix}acct_billing",
            )

    render_anomalies_section(
        usage_df,
        view_period_df=usage_df,
        key_suffix=f"{widget_key_prefix}analysis_account",
    )


def render_rate_compare_tab(
    usage_df: pd.DataFrame,
    *,
    contract_id: str,
    widget_key_prefix: str = "",
) -> None:
    """Rate compare tab — same UI as Upload → Results."""
    kp = widget_key_prefix
    available_years = build_year_options(usage_df)
    rc_y1, rc_y2, _rc_hdr_spacer = st.columns([1, 1, 3])
    with rc_y1:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}rc_year")
    with rc_y2:
        schedule_id = st.selectbox("Schedule", sorted(SCHEDULE_FUNCS.keys()), key=f"{kp}rc_schedule")

    df_year, year_label = filter_by_year_option(usage_df, selected_year)
    df_year_for_anomalies = df_year.copy()
    df_year["bill_period_end"] = df_year["bill_period_end"].dt.strftime("%Y-%m-%d")

    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
    else:
        try:
            schedule_out = SCHEDULE_FUNCS[schedule_id](df_year.copy(), None)
            base_cols = ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"]
            avail = [c for c in base_cols if c in df_year.columns]
            merged = pd.concat(
                [df_year[avail].reset_index(drop=True), schedule_out.reset_index(drop=True)], axis=1,
            )
            merged = merged.loc[:, ~merged.columns.duplicated()].reset_index(drop=True)

            calc_col = f"ve{schedule_id}_calculated_amount"
            actual_total = df_year["charges"].sum()
            calc_total = merged[calc_col].sum() if calc_col in merged.columns else 0
            total_savings = actual_total - calc_total
            savings_cls = "kpi-positive" if total_savings >= 0 else "kpi-negative"
            savings_label = "Total Savings" if total_savings >= 0 else "Total Overpaid"

            rc_kpi_html = (
                kpi_card(f"Actual Charges ({year_label})", f"${actual_total:,.2f}")
                + kpi_card(f"VE-{schedule_id} Calculated", f"${calc_total:,.2f}")
                + kpi_card(savings_label, f"${abs(total_savings):,.2f}", cls=savings_cls)
            )
            st.markdown(
                f'<div class="kpi-row compare-kpi-band">{rc_kpi_html}</div>',
                unsafe_allow_html=True,
            )

            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown('<div class="section-title">Detailed Comparison</div>', unsafe_allow_html=True)
            st.caption("Each billing period with usage, charges, and calculated breakdown; last row is **TOTAL**. Download for full detail.")
            merged_totals = add_total(merged)
            merged_totals = merged_totals.loc[:, ~merged_totals.columns.str.contains("case_type", case=False)]
            merged_totals = reorder_first(merged_totals)

            _rc_key_safe = re.sub(r"[^\w]+", "_", str(year_label))[:32]
            _rc_full_cfg = merged_comparison_column_config(merged_totals)
            render_dataframe_with_fixed_total(
                merged_totals,
                period_col="bill_period_end",
                column_config=_rc_full_cfg,
                key_prefix=f"{kp}rc_full_{schedule_id}_{_rc_key_safe}",
            )
            st.download_button(
                "Download full detail (Excel)",
                data=export_excel(merged_totals),
                file_name=f"{contract_id}_VE{schedule_id}_{year_label}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_full_rc_{schedule_id}_{str(year_label).replace(' ', '_')[:48]}",
            )
            rc_summary = monthly_calculated_view_df(merged_totals)
            st.markdown('<div class="section-title">Monthly summary (period, usage, charges, calculated)</div>', unsafe_allow_html=True)
            st.caption(
                "Shorter table: dates, usage, charges, and key calculated columns. Use **Download full detail** above for everything."
            )
            rc_disp = rc_summary.copy()
            if "bill_period_end" in rc_disp.columns:
                b = rc_disp["bill_period_end"]
                is_tot = b.astype(str).str.upper() == "TOTAL"
                rc_disp = rc_disp.copy()
                rc_disp.loc[~is_tot, "bill_period_end"] = pd.to_datetime(
                    b[~is_tot], errors="coerce"
                ).dt.strftime("%Y-%m-%d")
            render_dataframe_with_fixed_total(
                rc_disp,
                period_col="bill_period_end",
                column_config=monthly_view_column_config(rc_disp),
                key_prefix=f"{kp}rc_sum_{schedule_id}_{_rc_key_safe}",
            )
            st.download_button(
                "Download monthly summary (Excel)",
                data=export_excel(rc_summary),
                file_name=f"{contract_id}_VE{schedule_id}_{year_label}_monthly_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_sum_rc_{schedule_id}_{str(year_label).replace(' ', '_')[:48]}",
            )
            gap_df = monthly_actual_vs_calculated_gaps(merged, calc_col)
            gd_wb = pd.DataFrame()
            if not gap_df.empty:
                st.markdown(
                    '<div class="section-title">Actual vs calculated — monthly gaps</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Per bill: actual minus VE calculated. Positive = billed more than the model; "
                    "**gap %** is vs calculated (not actual)."
                )
                gd = gap_df.copy()
                gd["bill_period_end"] = pd.to_datetime(
                    gd["bill_period_end"], errors="coerce"
                ).dt.strftime("%Y-%m-%d")
                gd_wb = gd.copy()
                st.dataframe(
                    gd,
                    width="stretch",
                    height=460,
                    hide_index=True,
                    column_config={
                        "bill_period_end": st.column_config.TextColumn("bill_period_end"),
                        "actual_charges": st.column_config.NumberColumn(format="$%.2f"),
                        "calculated": st.column_config.NumberColumn(format="$%.2f"),
                        "gap_actual_minus_calculated": st.column_config.NumberColumn(
                            format="$%.2f",
                        ),
                        "gap_pct_of_calculated": st.column_config.NumberColumn(format="%.1f"),
                    },
                )
                _yl = re.sub(r"[^\w]+", "_", str(year_label))[:32]
                st.download_button(
                    "Download monthly gaps (Excel)",
                    data=export_excel(gd),
                    file_name=f"{contract_id}_VE{schedule_id}_{_yl}_gaps.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{kp}dl_gap_rc_{schedule_id}_{_yl}",
                )
            _yl_wb = re.sub(r"[^\w]+", "_", str(year_label))[:28]
            _wb_rc = {"Full_detail": merged_totals, "Monthly_summary": rc_summary}
            if not gd_wb.empty:
                _wb_rc["Gaps"] = gd_wb
            st.download_button(
                "Download one workbook (all tables on this tab)",
                data=export_excel_multi_sheet(_wb_rc),
                file_name=f"{contract_id}_VE{schedule_id}_{_yl_wb}_workbook.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_wb_rc_{schedule_id}_{_yl_wb}",
            )
            render_anomalies_section(
                usage_df,
                view_period_df=df_year_for_anomalies,
                title=f"Anomalies — {year_label}",
                key_suffix=f"{kp}rc_{schedule_id}_{str(year_label).replace(' ', '_')[:24]}",
            )
        except Exception as e:
            st.error(f"Schedule VE-{schedule_id} error: {e}")


def render_schedule_compare_tab(
    usage_df: pd.DataFrame,
    *,
    contract_id: str,
    widget_key_prefix: str = "",
) -> None:
    """Schedule compare tab — same UI as Upload → Results."""
    kp = widget_key_prefix
    available_years3 = build_year_options(usage_df)
    ctrl3a, ctrl3b = st.columns([1, 2])
    with ctrl3a:
        selected_year3 = st.selectbox("Year", available_years3, key=f"{kp}sc_year")
    with ctrl3b:
        selected_schedules = st.multiselect(
            "Schedules to Compare",
            options=sorted(SCHEDULE_FUNCS.keys()),
            default=sorted(SCHEDULE_FUNCS.keys()),
            key=f"{kp}sc_schedules",
        )

    df_year3, year_label3 = filter_by_year_option(usage_df, selected_year3)
    df_year3_for_anomalies = df_year3.copy()
    df_year3["bill_period_end"] = df_year3["bill_period_end"].dt.strftime("%Y-%m-%d")

    if not selected_schedules:
        st.warning("Select at least one schedule to compare.")
    elif df_year3.empty:
        st.warning(f"No billing data found for {year_label3}.")
    else:
        actual_total3 = df_year3["charges"].sum()
        base_cols = ["bill_period_end", "usage_kwh", "charges"]
        comp = df_year3[[c for c in base_cols if c in df_year3.columns]].reset_index(drop=True).copy()

        schedule_totals = {}
        for sid in selected_schedules:
            try:
                out = SCHEDULE_FUNCS[sid](df_year3.copy(), None)
                calc_col = f"ve{sid}_calculated_amount"
                if calc_col in out.columns:
                    comp[f"VE-{sid} Calculated ($)"] = out[calc_col].reset_index(drop=True)
                    schedule_totals[f"VE-{sid}"] = out[calc_col].sum()
                else:
                    st.warning(f"Schedule VE-{sid}: calculated_amount column not found.")
            except Exception as e:
                st.warning(f"Schedule VE-{sid} skipped: {e}")

        if schedule_totals:
            sc_kpi_html = kpi_card("Actual Charges", f"${actual_total3:,.2f}", year_label3)
            for sched_name, calc_val in schedule_totals.items():
                diff = actual_total3 - calc_val
                cls = "kpi-positive" if diff >= 0 else "kpi-negative"
                sc_kpi_html += kpi_card(
                    sched_name,
                    f"${calc_val:,.2f}",
                    f"Save ${diff:,.2f}" if diff >= 0 else f"Over ${abs(diff):,.2f}",
                    cls,
                )
            st.markdown(
                f'<div class="kpi-row compare-kpi-band">{sc_kpi_html}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("<hr>", unsafe_allow_html=True)

        st.markdown('<div class="section-title">Monthly calculated amounts</div>', unsafe_allow_html=True)
        st.caption(
            "One calculated column per schedule. **Monthly summary** is the essentials; **full comparison** includes all columns and a **TOTAL** row."
        )
        comp = comp.loc[:, ~comp.columns.str.contains("case_type", case=False)]
        result = reorder_first(add_total(comp))
        summary_sc = monthly_calculated_view_df(result)

        display = summary_sc.copy()
        num_cols = display.select_dtypes(include=["float", "int"]).columns
        display[num_cols] = display[num_cols].round(2)
        if "bill_period_end" in display.columns:
            b = display["bill_period_end"]
            is_tot = b.astype(str).str.upper() == "TOTAL"
            display = display.copy()
            display.loc[~is_tot, "bill_period_end"] = pd.to_datetime(
                b[~is_tot], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
        _sc_key_safe = re.sub(r"[^\w]+", "_", str(year_label3))[:40]
        render_dataframe_with_fixed_total(
            display,
            period_col="bill_period_end",
            column_config=monthly_view_column_config(display),
            key_prefix=f"{kp}sc_monthly_{_sc_key_safe}",
        )
        st.download_button(
            "Download monthly summary (Excel)",
            data=export_excel(summary_sc),
            file_name=f"{contract_id}_schedule_comparison_{year_label3}_monthly_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_sum_sc_{str(year_label3).replace(' ', '_')[:48]}",
        )
        st.download_button(
            "Download full comparison (Excel)",
            data=export_excel(result),
            file_name=f"{contract_id}_schedule_comparison_{year_label3}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_full_sc_{str(year_label3).replace(' ', '_')[:48]}",
        )
        gap_sc = schedule_compare_gap_table(comp, selected_schedules)
        gsd_wb = pd.DataFrame()
        if not gap_sc.empty:
            st.markdown(
                '<div class="section-title">Gaps vs each schedule (actual minus calculated)</div>',
                unsafe_allow_html=True,
            )
            st.caption("Same periods as the table above; one gap column per VE schedule.")
            gsd = gap_sc.copy()
            gsd["bill_period_end"] = pd.to_datetime(
                gsd["bill_period_end"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            gsd_wb = gsd.copy()
            gap_cfg = {}
            for c in gsd.columns:
                if c == "bill_period_end":
                    gap_cfg[c] = st.column_config.TextColumn(c)
                elif "gap_vs" in c:
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
                elif "charges" in c.lower():
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="$%.2f")
                elif "usage" in c.lower() or "kwh" in c.lower():
                    gap_cfg[c] = st.column_config.NumberColumn(c, format="%.0f")
                else:
                    gap_cfg[c] = st.column_config.TextColumn(c)
            st.dataframe(gsd, width="stretch", height=460, hide_index=True, column_config=gap_cfg)
            _y3 = re.sub(r"[^\w]+", "_", str(year_label3))[:32]
            st.download_button(
                "Download schedule gap table (Excel)",
                data=export_excel(gsd),
                file_name=f"{contract_id}_schedule_gaps_{_y3}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{kp}dl_gap_sc_{_y3}",
            )
        _y3_wb = re.sub(r"[^\w]+", "_", str(year_label3))[:28]
        _wb_sc = {"Full_comparison": result, "Monthly_summary": summary_sc}
        if not gsd_wb.empty:
            _wb_sc["Gaps"] = gsd_wb
        st.download_button(
            "Download one workbook (all tables on this tab)",
            data=export_excel_multi_sheet(_wb_sc),
            file_name=f"{contract_id}_schedule_compare_{_y3_wb}_workbook.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{kp}dl_wb_sc_{_y3_wb}",
        )
        render_anomalies_section(
            usage_df,
            view_period_df=df_year3_for_anomalies,
            title=f"Anomalies — {year_label3}",
            key_suffix=f"{kp}sc_{str(year_label3).replace(' ', '_')[:28]}",
        )


def build_year_options(df: pd.DataFrame) -> list:
    years = sorted(df["bill_period_end"].dt.year.dropna().unique().astype(int), reverse=True)
    return ["All Years", "Last 12 Months", *years]


def filter_by_year_option(df: pd.DataFrame, selected_option):
    if selected_option == "All Years":
        return df.copy(), "All Years"

    if selected_option == "Last 12 Months":
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

    return df[df["bill_period_end"].dt.year == selected_option].copy(), str(selected_option)





# ---------------------------------------------------
# Past usage bills + ops uploads (API only — no src.* imports)
# ---------------------------------------------------

def _pastusage_batches_api_payload(batches_to_load: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, r in batches_to_load.iterrows():
        row: dict = {"bill_year": str(r["bill_year"])}
        bid = r.get("batch_id")
        if bid is not None and pd.notna(bid) and str(bid).strip():
            row["batch_id"] = str(bid).strip()
        ua = r.get("uploaded_at")
        if ua is not None and pd.notna(ua):
            row["uploaded_at"] = pd.Timestamp(ua).isoformat()
        rows.append(row)
    return rows


def fetch_uploaded_bill_options() -> pd.DataFrame:
    r = _api_request("get", "/api/bills")
    rows = r.json()
    _cols = [
        "batch_id",
        "source_pdf",
        "account_number",
        "customer_name",
        "bill_year",
        "uploaded_at",
        "row_count",
    ]
    if not rows:
        return pd.DataFrame(columns=_cols)
    norm = []
    for x in rows:
        norm.append(
            {
                "batch_id": x.get("batch_id"),
                "source_pdf": x.get("source_pdf"),
                "account_number": x.get("accountNumber"),
                "customer_name": x.get("accountName"),
                "bill_year": str(x.get("year", "")),
                "uploaded_at": pd.to_datetime(x["uploaded_at"]) if x.get("uploaded_at") else pd.NaT,
                "row_count": int(x.get("row_count", 0)),
            }
        )
    return pd.DataFrame(norm)


def fetch_version_options(table_name: str) -> pd.DataFrame:
    """Load tariff/rider version rows from the API."""
    empty = pd.DataFrame(columns=["version", "effective_date", "uploaded_at"])
    try:
        r = requests.get(f"{BACKEND_URL}/api/versions/{table_name}", timeout=60)
        if r.status_code != 200:
            return empty
        data = r.json()
        if not data:
            return empty
        return pd.DataFrame(data)
    except Exception:
        return empty


def add_recalc_history(entry: dict, *, session_key: str = "pastusage_recalc_history") -> None:
    hist = st.session_state.setdefault(session_key, [])
    hist.insert(0, entry)
    st.session_state[session_key] = hist[:5]


def render_ops_tariff_panel(*, key_prefix: str = "ltariff_") -> None:
    st.markdown('<div class="section-title">TARIFFS VERSION UPLOAD</div>', unsafe_allow_html=True)
    st.markdown('<div class="form-panel"><strong>Required</strong>: Tariff workbook and effective date.</div>', unsafe_allow_html=True)

    tariffs_file = st.file_uploader(
        "Select tariffs Excel file",
        type=["xlsx", "xls"],
        key=f"{key_prefix}tariffs_uploader",
    )
    tariffs_effective_date = st.date_input(
        "Tariff effective date",
        key=f"{key_prefix}tariffs_effective_date",
    )
    if st.button("Upload Tariffs Version", type="primary", key=f"{key_prefix}upload_tariffs_btn"):
        if tariffs_file is None:
            st.warning("Upload a tariffs Excel file first.")
        elif tariffs_effective_date > pd.Timestamp.today().date():
            st.warning("Effective date cannot be in the future.")
        else:
            try:
                safe_name = Path(tariffs_file.name).name
                if not safe_name.lower().endswith((".xlsx", ".xls")):
                    st.warning("Only Excel files are supported.")
                else:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    files = {"file": (safe_name, tariffs_file.getbuffer(), mime)}
                    params = {"effective_date": tariffs_effective_date.isoformat()}
                    _api_request("post", "/api/tariffs/upload", files=files, params=params)
                    try:
                        _schedule_options.clear()
                        _calc_sources.clear()
                    except (AttributeError, TypeError):
                        pass
                    st.success(f"Tariffs uploaded successfully: {safe_name}")
                    st.caption("Tariff workbook is saved and versioned. Use **Upload latest riders** when you are ready.")
            except Exception as exc:
                st.error(f"Tariff upload failed: {exc}")


def render_ops_riders_panel(*, key_prefix: str = "lriders_") -> None:
    st.markdown('<div class="section-title">RIDERS VERSION UPLOAD</div>', unsafe_allow_html=True)
    st.markdown('<div class="form-panel"><strong>Required</strong>: Riders workbook and effective date.</div>', unsafe_allow_html=True)

    riders_file = st.file_uploader(
        "Select riders Excel file",
        type=["xlsx", "xls"],
        key=f"{key_prefix}riders_uploader",
    )
    riders_effective_date = st.date_input(
        "Rider effective date",
        key=f"{key_prefix}riders_effective_date",
    )
    if st.button("Upload Riders Version", type="primary", key=f"{key_prefix}upload_riders_btn"):
        if riders_file is None:
            st.warning("Upload a riders Excel file first.")
        elif riders_effective_date > pd.Timestamp.today().date():
            st.warning("Effective date cannot be in the future.")
        else:
            try:
                safe_name = Path(riders_file.name).name
                if not safe_name.lower().endswith((".xlsx", ".xls")):
                    st.warning("Only Excel files are supported.")
                else:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    files = {"file": (safe_name, riders_file.getbuffer(), mime)}
                    params = {"effective_date": riders_effective_date.isoformat()}
                    _api_request("post", "/api/riders/upload", files=files, params=params)
                    try:
                        _calc_sources.clear()
                    except (AttributeError, TypeError):
                        pass
                    st.success(f"Riders uploaded successfully: {safe_name}")
                    st.caption("Riders workbook is saved and versioned. Open **Past usage bills** to recalculate when you are ready.")
            except Exception as exc:
                st.error(f"Rider upload failed: {exc}")


def render_ops_recalc_panel(
    *,
    key_prefix: str = "pastusage_",
    result_df_key: str = "pastusage_recalc_result_df",
    result_name_key: str = "pastusage_recalc_result_name",
    schedule_ids_key: str = "pastusage_recalc_schedule_ids",
    history_session_key: str = "pastusage_recalc_history",
) -> None:
    st.markdown('<div class="section-title">RUN RECALCULATION</div>', unsafe_allow_html=True)
    st.caption(
        "Pick an account and **billing period** (a single year, last 12 months, or all years). "
        "Then choose rate sources and schedules before you run."
    )

    try:
        bill_options = fetch_uploaded_bill_options()
    except Exception as exc:
        st.error(f"Failed to load uploaded bill options: {exc}")
        bill_options = pd.DataFrame()

    if bill_options.empty:
        st.info(
            "**No saved bills yet.** Add bills from **Upload usage bills**, or continue when your data is available. "
            "Then pick an account and billing period here."
        )
    else:
        display_all = bill_options.copy()
        display_all["bill_year"] = display_all["bill_year"].astype(str)

        acct_choices = (
            display_all.drop_duplicates(subset=["account_number", "customer_name"])
            .sort_values(["account_number", "customer_name"])
            .reset_index(drop=True)
        )
        acct_choices["acct_label"] = (
            acct_choices["account_number"].astype(str).str.strip()
            + " — "
            + acct_choices["customer_name"].astype(str).str.strip()
        )
        acct_labels = acct_choices["acct_label"].tolist()
        _acct_sb_key = f"{key_prefix}recalc_account_option"
        if _acct_sb_key in st.session_state and st.session_state[_acct_sb_key] not in acct_labels:
            del st.session_state[_acct_sb_key]
        selected_label = st.selectbox(
            "Account",
            options=acct_labels,
            key=_acct_sb_key,
        )
        st.caption(
            "Open the dropdown to search: matching rows appear below as you type (numbers, letters, or symbols)."
        )

        acct_row = acct_choices.loc[acct_choices["acct_label"] == selected_label].iloc[0]

        for_account = display_all[
            (display_all["account_number"].astype(str).str.strip() == str(acct_row["account_number"]).strip())
            & (display_all["customer_name"].astype(str).str.strip() == str(acct_row["customer_name"]).strip())
        ]
        cal_years = sorted(
            {int(y) for y in for_account["bill_year"].astype(str) if str(y).strip().isdigit()},
            reverse=True,
        )
        period_options: list = ["All Years", "Last 12 Months", *cal_years]
        selected_period = st.selectbox(
            "Billing period",
            options=period_options,
            key=f"{key_prefix}recalc_year_option",
        )

        batches_to_load: pd.DataFrame | None = None
        selected_row: pd.Series | None = None

        if selected_period in ("All Years", "Last 12 Months"):
            st.caption(
                "Combines all saved uploads for this account. If the same bill date appears more than once, "
                "the newest version is kept."
            )
            batches_to_load = for_account.sort_values("uploaded_at", ascending=True, na_position="first")
            if batches_to_load.empty:
                st.warning("No batches found for this account.")
            else:
                selected_row = batches_to_load.iloc[-1]
        else:
            batches = for_account[for_account["bill_year"].astype(str) == str(selected_period)].copy()
            batches["uploaded_at_label"] = batches["uploaded_at"].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else "N/A"
            )

            if batches.empty:
                st.warning("No batch found for this account and calendar year.")
            elif len(batches) == 1:
                selected_row = batches.iloc[0]
                batches_to_load = batches
            else:
                batches["session_label"] = (
                    "Uploaded "
                    + batches["uploaded_at_label"]
                    + " · "
                    + batches["row_count"].astype(str)
                    + " row(s)"
                )
                session_label = st.selectbox(
                    "Upload session (same account and year)",
                    options=batches["session_label"].tolist(),
                    key=f"{key_prefix}recalc_session_option",
                )
                selected_row = batches.loc[batches["session_label"] == session_label].iloc[0]
                batches_to_load = batches.loc[batches["session_label"] == session_label]

        if selected_row is not None and batches_to_load is not None:
            try:
                tariff_versions = fetch_version_options("tariff_rates")
            except Exception as exc:
                st.error(f"Failed to load tariff versions: {exc}")
                tariff_versions = pd.DataFrame()
            try:
                rider_versions = fetch_version_options("rider_rates")
            except Exception as exc:
                st.error(f"Failed to load rider versions: {exc}")
                rider_versions = pd.DataFrame()

            try:
                sources = _calc_sources(BACKEND_URL)
            except Exception:
                sources = {}

            tariff_choices: list[tuple[str, str, object]] = []
            if sources.get("tariff_workbook_on_disk"):
                tariff_choices.append(("Current tariff file (on disk)", "file", "disk"))
            for _, row in tariff_versions.iterrows():
                v = int(row["version"])
                tariff_choices.append((f"Database tariff version {v}", "db", v))

            rider_choices: list[tuple[str, str, object]] = []
            if sources.get("riders_file_on_disk"):
                rider_choices.append(("Current riders file (on disk)", "file", None))
            for _, row in rider_versions.iterrows():
                v = int(row["version"])
                rider_choices.append((f"Database rider version {v}", "db", v))

            if not tariff_choices:
                st.warning(
                    "No tariff source available. Upload tariffs via **Upload latest tariff** "
                    "or ensure the database has tariff versions."
                )
            if not rider_choices:
                st.warning(
                    "No rider source available. Upload riders via **Upload latest riders** "
                    "or ensure the database has rider versions."
                )

            col_a, col_b = st.columns(2)
            with col_a:
                if tariff_choices:
                    tariff_labels = [c[0] for c in tariff_choices]
                    t_pick = st.selectbox(
                        "Tariff source",
                        options=tariff_labels,
                        index=0,
                        key=f"{key_prefix}recalc_tariff_source",
                    )
                    tariff_kind, tariff_payload = next((c[1], c[2]) for c in tariff_choices if c[0] == t_pick)
                else:
                    tariff_kind, tariff_payload = None, None

            with col_b:
                if rider_choices:
                    rider_labels = [c[0] for c in rider_choices]
                    r_pick = st.selectbox(
                        "Rider source",
                        options=rider_labels,
                        index=0,
                        key=f"{key_prefix}recalc_rider_source",
                    )
                    rider_kind, rider_payload = next((c[1], c[2]) for c in rider_choices if c[0] == r_pick)
                else:
                    rider_kind, rider_payload = None, None

            schedule_options = sorted(_schedule_options(BACKEND_URL))
            selected_schedule_ids = st.multiselect(
                "Schedules to calculate",
                options=schedule_options,
                default=schedule_options,
                key=f"{key_prefix}recalc_schedules",
            )

            if st.button("Run recalculation", type="primary", key=f"{key_prefix}recalc_all_btn"):
                if not tariff_choices or not rider_choices:
                    st.warning("A tariff source and a rider source are both required.")
                elif not selected_schedule_ids:
                    st.warning("Select at least one schedule.")
                else:
                    try:
                        with st.spinner("Running recalculation..."):
                            bid_val = selected_row.get("batch_id")
                            bid_use = (
                                str(bid_val).strip()
                                if bid_val is not None and pd.notna(bid_val)
                                else ""
                            )
                            if tariff_kind == "file":
                                tariff_api_source = "file"
                                tariff_api_version = None
                            else:
                                tariff_api_source = "db"
                                tariff_api_version = int(tariff_payload)

                            if rider_kind == "file":
                                rider_api_source = "file"
                                rider_api_version = None
                            else:
                                rider_api_source = "db"
                                rider_api_version = int(rider_payload)

                            batches_pl = _pastusage_batches_api_payload(batches_to_load)
                            if selected_period == "All Years":
                                period_kw: dict = {"period": "All Years"}
                                period_slug = "all_years"
                                period_hist = "All Years"
                            elif selected_period == "Last 12 Months":
                                period_kw = {"period": "Last 12 Months"}
                                period_slug = "last_12_months"
                                period_hist = "Last 12 Months"
                            else:
                                period_kw = {"calendar_year": int(selected_period)}
                                period_slug = str(int(selected_period))
                                period_hist = str(int(selected_period))

                            body = {
                                "account_number": str(selected_row["account_number"]).strip(),
                                "batches": batches_pl,
                                "schedule_ids": list(selected_schedule_ids),
                                "tariff_source": tariff_api_source,
                                "tariff_version": tariff_api_version,
                                "rider_source": rider_api_source,
                                "rider_version": rider_api_version,
                                **period_kw,
                            }
                            r = _api_request("post", "/api/calculate", json=body)
                            recalc_result = pd.DataFrame(r.json()["records"])

                            st.session_state[result_df_key] = recalc_result
                            st.session_state[schedule_ids_key] = list(selected_schedule_ids)
                            sched_slug = "_".join(str(s) for s in sorted(selected_schedule_ids))
                            tariff_tag = "disk" if tariff_kind == "file" else f"v{int(tariff_payload)}"
                            rider_tag = "disk" if rider_kind == "file" else f"v{int(rider_payload)}"
                            safe_period = re.sub(r"[^\w\-]+", "_", str(period_slug))[:48]
                            st.session_state[result_name_key] = (
                                f"{selected_row['account_number']}_"
                                f"{safe_period}_"
                                f"tariff_{tariff_tag}_"
                                f"rider_{rider_tag}_"
                                f"ve{sched_slug}.xlsx"
                            )
                            add_recalc_history(
                                {
                                    "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "batch_id": bid_use[:16] if bid_use else "",
                                    "account": str(selected_row["account_number"]),
                                    "year": period_hist[:120],
                                    "tariff": tariff_tag,
                                    "rider": rider_tag,
                                    "schedules": ",".join(str(s) for s in sorted(selected_schedule_ids)),
                                    "rows": int(len(recalc_result)),
                                },
                                session_key=history_session_key,
                            )
                            st.success("Recalculation completed.")
                            st.caption("Downloads, preview, anomalies, and run history are below.")
                    except Exception as exc:
                        st.error(f"Recalculation failed: {exc}")


def render_ops_export_panel(
    *,
    key_prefix: str = "pastusage_",
    result_df_key: str = "pastusage_recalc_result_df",
    result_name_key: str = "pastusage_recalc_result_name",
    schedule_ids_key: str = "pastusage_recalc_schedule_ids",
    history_session_key: str = "pastusage_recalc_history",
    anomalies_key_suffix: str = "pastusage_export",
) -> None:
    st.markdown('<div class="section-title">EXPORT AND HISTORY</div>', unsafe_allow_html=True)
    result_df = st.session_state.get(result_df_key)
    result_name = st.session_state.get(result_name_key, "recalculation.xlsx")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("Rows Processed", f"{len(result_df):,}")
        _sched_run = st.session_state.get(schedule_ids_key) or []
        _n_all = len(_schedule_options(BACKEND_URL))
        metric_b.metric(
            "Schedules Run",
            str(len(_sched_run)) if _sched_run else str(_n_all),
        )
        metric_c.metric("Export File", result_name)

        summary_re = monthly_calculated_view_df(result_df)
        preview = summary_re.copy()
        if "bill_period_end" in preview.columns:
            preview["bill_period_end"] = pd.to_datetime(
                preview["bill_period_end"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
        st.markdown(
            '<div class="section-title">Monthly calculated amounts (preview)</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "**Monthly summary** — bill dates, usage, charges, and calculated totals. "
            "**Full recalculation** — all columns from the recalculation run."
        )
        st.dataframe(
            preview,
            width="stretch",
            height=420,
            hide_index=True,
            column_config=monthly_view_column_config(preview),
        )
        base_name = Path(result_name).stem
        st.download_button(
            "Download monthly summary (Excel)",
            data=export_excel(summary_re),
            file_name=f"{base_name}_monthly_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_download_summary_btn",
        )
        st.download_button(
            "Download full recalculation (Excel)",
            data=export_excel(result_df),
            file_name=result_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_download_btn",
        )
        render_anomaly_detection_settings_expander()
        render_anomalies_section(
            result_df,
            view_period_df=result_df,
            title="Anomalies (recalculation output)",
            key_suffix=anomalies_key_suffix,
        )
        try:
            anom_combined = build_anomalies_export_table(result_df, view_period_df=result_df)
        except Exception:
            anom_combined = pd.DataFrame()
        st.download_button(
            "Download one workbook (monthly + full + anomalies)",
            data=export_excel_multi_sheet(
                {
                    "Monthly_summary": summary_re,
                    "Full_recalculation": result_df,
                    "Anomalies": anom_combined,
                }
            ),
            file_name=f"{base_name}_workbook_monthly_full_anomalies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_download_workbook_monthly_full_anomalies_btn",
        )
    else:
        st.info(
            "No results yet. Run **Run recalculation** first (pick account, period, sources, then run). "
            "Downloads and anomalies appear here when finished."
        )

    run_history = st.session_state.get(history_session_key, [])
    if run_history:
        st.markdown('<div class="section-title">Recent recalculation runs</div>', unsafe_allow_html=True)
        hist_df = pd.DataFrame(run_history)
        st.dataframe(hist_df, width="stretch", hide_index=True)
        st.download_button(
            "Download run history (Excel)",
            data=export_excel(hist_df),
            file_name="recalc_run_history.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_history_download",
        )


def render_past_usage_bills_page() -> None:
    """Single scrollable page: recalculation form, then export/history (no tabs)."""
    render_ops_recalc_panel()
    st.divider()
    render_ops_export_panel()

# ---------------------------------------------------
# Session state defaults
# ---------------------------------------------------
if "page" not in st.session_state:
    st.session_state["page"] = "upload"
if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "Dark"

for _ak, _av in (
    ("anom_yoy_pct", 0.5),
    ("anom_abs_daily", 5.0),
    ("anom_bill_mult", 2.5),
    ("anom_bill_delta_cpk", 0.05),
    ("anom_bill_min_kwh", 30.0),
    ("anom_charge_mult", 2.5),
    ("anom_charge_min_usd", 100.0),
):
    st.session_state.setdefault(_ak, _av)

if st.session_state.get("page") == "operations_hub":
    st.session_state["page"] = "op_past"

with st.sidebar:
    st.markdown("### Display")
    st.session_state["ui_theme"] = st.radio(
        "Theme",
        options=["Dark", "Light"],
        index=0 if st.session_state["ui_theme"] == "Dark" else 1,
        key="ui_theme_selector",
        horizontal=True,
    )
    st.markdown("### Navigate")
    st.markdown(
        '<p class="sidebar-nav-lead">These pages do not share your entries or results.</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload usage bills (PDF)</strong> — <span>Add billing PDFs.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload usage bills", use_container_width=True, key="sidebar_nav_upload_bills"):
        st.session_state["page"] = "upload"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload latest tariff</strong> — <span>Upload the schedules Excel file.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload latest tariff", use_container_width=True, key="sidebar_nav_tariff"):
        st.session_state["page"] = "op_tariff"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Upload latest riders</strong> — <span>Upload the riders Excel file.</span></p>',
        unsafe_allow_html=True,
    )
    if st.button("Upload latest riders", use_container_width=True, key="sidebar_nav_riders"):
        st.session_state["page"] = "op_riders"
        st.rerun()
    st.markdown('<div class="sidebar-nav-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(
        '<p class="sidebar-nav-hint"><strong>Past usage bills (recalculate + export)</strong> — '
        "<span>Run saved usage through selected tariff/rider versions and export.</span></p>",
        unsafe_allow_html=True,
    )
    if st.button("Past usage bills", use_container_width=True, key="sidebar_nav_past"):
        st.session_state["page"] = "op_past"
        st.rerun()

if st.session_state["ui_theme"] == "Light":
    st.markdown(
        """
<style>
/* Light: warm white background, black text */
[data-testid="stAppViewContainer"] { background: #f7f4ef !important; color: #0a0a0a !important; }
[data-testid="stHeader"], [data-testid="stDecoration"], [data-testid="stToolbar"] {
    background: #f7f4ef !important;
}
section[data-testid="stSidebar"] {
    background-color: #faf8f5 !important;
    border-right: 1px solid #e8e0d6 !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] .stMarkdown {
    color: #0a0a0a !important;
}
section[data-testid="stSidebar"] p.sidebar-nav-lead {
    color: #5c534c !important;
    line-height: 1.6 !important;
    font-size: 0.76rem !important;
}
section[data-testid="stSidebar"] p.sidebar-nav-hint {
    color: #4b5563 !important;
    line-height: 1.5 !important;
    font-size: 0.74rem !important;
}
section[data-testid="stSidebar"] p.sidebar-nav-hint strong { color: #111111 !important; }
section[data-testid="stSidebar"] p.sidebar-nav-hint span { color: #5c534c !important; }

.main, .main p, .main span, .main label, .stMarkdown, [data-testid="stMarkdownContainer"] p {
    color: #111111 !important;
}

.block-container {
    padding-top: 2.75rem !important;
}
section.main > div {
    padding-top: 0.35rem !important;
}
.premium-strip {
    padding: 0.85rem 1rem 0.8rem !important;
    margin: 0.5rem 0 1rem !important;
    line-height: 1.55 !important;
    overflow: visible !important;
}

.hero, .results-nav, .kpi-card, .info-item, .form-panel, .premium-strip {
    background: #faf8f5 !important;
    border-color: #e8e0d6 !important;
    color: #0a0a0a !important;
}

h1, h2, h3, h4, h5, h6, p, span, div, label, small {
    color: #111111 !important;
}
.section-title, .kpi-label, .hero-sub, .results-nav-file, .hero-meta {
    color: #404040 !important;
}
.kpi-value, .info-item-value, .results-nav-title {
    color: #000000 !important;
}
.hero-title {
    background: none !important;
    -webkit-text-fill-color: #000000 !important;
    color: #000000 !important;
}

[data-testid="stTabs"] [role="tablist"] {
    background: #f0ebe3 !important;
    border-color: #e8e0d6 !important;
    box-shadow: none !important;
}
[data-testid="stTabs"] [role="tab"],
[data-testid="stTabs"] button[data-baseweb="tab"] {
    color: #404040 !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stTabs"] [role="tab"] *,
[data-testid="stTabs"] button[data-baseweb="tab"] * {
    color: inherit !important;
    -webkit-text-fill-color: inherit !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"],
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    background: #ffffff !important;
    color: #000000 !important;
    border: 1px solid #d4ccc0 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] *,
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stTabs"] [role="tab"]:hover:not([aria-selected="true"]),
[data-testid="stTabs"] button[data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    background: #ebe6de !important;
    color: #000000 !important;
}
[data-testid="stTabs"] [role="tab"]:focus,
[data-testid="stTabs"] [role="tab"]:focus-visible,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
    outline: none !important;
}
[data-testid="stTabs"] [role="tab"]:focus-visible,
[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
    box-shadow: 0 0 0 2px #a8a29e !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background: #57534e !important;
}

[data-baseweb="select"] > div,
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input {
    background: #ffffff !important;
    border-color: #d4ccc0 !important;
    color: #0a0a0a !important;
}
[data-baseweb="select"] * {
    color: #0a0a0a !important;
}
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label {
    color: #262626 !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: #faf8f5 !important;
    border-color: #cfc6b8 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span:first-child,
[data-testid="stFileUploaderDropzoneInstructions"] small {
    color: #262626 !important;
}
[data-testid="stFileUploaderDropzone"] svg {
    color: #404040 !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: #0a0a0a !important;
    color: #faf8f5 !important;
    border-color: #0a0a0a !important;
}

[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]) {
    background: #0a0a0a !important;
    color: #faf8f5 !important;
    border-color: #0a0a0a !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #faf8f5 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]) * {
    color: #faf8f5 !important;
    -webkit-text-fill-color: #faf8f5 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):hover {
    background: #262626 !important;
    border-color: #262626 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):hover * {
    color: #faf8f5 !important;
    -webkit-text-fill-color: #faf8f5 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):focus-visible {
    box-shadow: 0 0 0 2px #a8a29e !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled,
[data-testid="stButton"] > button[kind="primary"][disabled],
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] {
    background: #d6d3d1 !important;
    color: #57534e !important;
    border-color: #a8a29e !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #57534e !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled *,
[data-testid="stButton"] > button[kind="primary"][disabled] *,
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] * {
    color: #57534e !important;
    -webkit-text-fill-color: #57534e !important;
}
[data-testid="stDownloadButton"] > button {
    background: #faf8f5 !important;
    color: #0a0a0a !important;
    border: 1px solid #d4ccc0 !important;
}
[data-testid="stDownloadButton"] > button * {
    color: #0a0a0a !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #ffffff !important;
    border-color: #a8a29e !important;
}
[data-testid="stDownloadButton"] > button:hover * {
    color: #0a0a0a !important;
}

[data-testid="stButton"] > button[kind="secondary"] {
    background: #ffffff !important;
    color: #0a0a0a !important;
    border-color: #d4ccc0 !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover {
    color: #000000 !important;
    border-color: #a8a29e !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid #e8e0d6 !important;
    border-radius: 10px !important;
}

.results-nav-mark { background: #0a0a0a !important; }

[data-testid="stMetric"] label { color: #525252 !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #000000 !important; }

[data-testid="stExpander"] summary { color: #0a0a0a !important; }

.kpi-positive { color: #15803d !important; }
.kpi-negative { color: #b91c1c !important; }

[data-testid="stAlert"] { background-color: #faf8f5 !important; color: #0a0a0a !important; border-color: #e8e0d6 !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { color: #111111 !important; }

[data-testid="stCaption"],
[data-testid="stWidgetLabel"] label,
label[data-testid="stWidgetLabel"] {
    color: #525252 !important;
}
[data-testid="stMarkdownContainer"] small { color: #57534e !important; }

[data-testid="stSidebar"] [data-baseweb="radio"] label,
[data-testid="stSidebar"] [data-baseweb="radio"] span {
    color: #0a0a0a !important;
}

[data-testid="stNumberInput"] label { color: #262626 !important; }
[data-testid="stNumberInput"] input {
    background: #ffffff !important;
    color: #0a0a0a !important;
    border-color: #d4ccc0 !important;
}

[data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] span { color: #111111 !important; }
[data-testid="stToggle"] label { color: #111111 !important; }

[data-testid="stTabs"] [role="tabpanel"],
[data-testid="stTabs"] [role="tabpanel"] p,
[data-testid="stTabs"] [role="tabpanel"] label {
    color: #111111 !important;
}

[data-testid="stButton"] > button[kind="secondary"] * {
    color: inherit !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover * {
    color: #000000 !important;
}

.main a, [data-testid="stMarkdownContainer"] a { color: #1d4ed8 !important; }

[data-testid="stExpander"] [data-testid="stVerticalBlock"] p,
[data-testid="stExpander"] [data-testid="stVerticalBlock"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #111111 !important;
}

[data-baseweb="popover"] {
    background-color: #ffffff !important;
    border: 1px solid #d4ccc0 !important;
}
[data-baseweb="popover"] li,
[data-baseweb="popover"] [role="option"] {
    color: #0a0a0a !important;
    background-color: #ffffff !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] [role="option"]:hover {
    background-color: #f0ebe3 !important;
}

hr { border-color: #e8e0d6 !important; }
</style>
        """,
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════
# PAGE 1 — UPLOAD
# ═══════════════════════════════════════════════════════════════
if st.session_state["page"] == "upload":

    # Hero
    st.markdown(
        '<div class="hero">'
        '<div class="hero-body">'
        '<div class="hero-title">Troy &amp; Banks</div>'
        '<div class="hero-sub">Dominion Energy &nbsp;·&nbsp; Virginia &nbsp;·&nbsp; Enterprise Billing Audit Platform</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Upload zone
    uploaded_files = st.file_uploader(
        "Upload Dominion Energy Billing PDF (select one or more files)",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="usage_bills_pdf_uploader",
    )

    if not uploaded_files:
        st.info(
            "Add one or more Dominion billing PDFs above. When processing finishes you’ll open **Results** to review "
            "**Analysis** or use the sidebar (**Past usage bills**, etc.) without uploading again."
        )

    if uploaded_files:
        batch_key = "|".join(f"{f.name}_{f.size}" for f in uploaded_files)
        if st.session_state.get("usage_bills_pdf_batch_key") != batch_key:
            st.session_state["usage_bills_pdf_batch_key"] = batch_key
            st.session_state["usage_df"] = None

        if st.session_state.get("usage_df") is None:
            last_usage = None
            last_profile = None
            last_name = None
            summaries = []
            errors = []
            for uf in uploaded_files:
                try:
                    with st.spinner(f"Processing {uf.name} - OCR and database sync"):
                        files = {"file": (uf.name, uf.getbuffer(), "application/pdf")}
                        r = _api_request("post", "/api/bills/upload", files=files)
                        payload = r.json()
                    usage_records = payload.get("usage_records") or []
                    if not usage_records:
                        errors.append("No usage tables extracted from one of the selected files.")
                        continue
                    usage_df = pd.DataFrame(usage_records)
                    if "bill_period_end" in usage_df.columns:
                        usage_df["bill_period_end"] = pd.to_datetime(usage_df["bill_period_end"], errors="coerce")
                    profile = payload.get("profile") or {}
                    batch_id = payload.get("batch_id", "")
                    summaries.append({"file": uf.name, "batch_id": batch_id, "rows": int(payload.get("rows_uploaded", 0))})
                    last_usage, last_profile, last_name = usage_df, profile, uf.name
                except Exception as e:
                    errors.append(str(e))
            for msg in errors:
                st.error(msg)
            if last_usage is None:
                st.stop()
            st.session_state["usage_df"] = last_usage
            st.session_state["profile"] = last_profile or {}
            if len(uploaded_files) == 1:
                st.session_state["pdf_name"] = last_name
            else:
                st.session_state["pdf_name"] = f"{len(uploaded_files)} PDFs (viewing last: {last_name})"
            st.session_state["multi_pdf_summaries"] = summaries

            st.session_state["page"] = "results"
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# PAGE — TARIFF UPLOAD (standalone)
# ═══════════════════════════════════════════════════════════════
elif st.session_state["page"] == "op_tariff":
    render_ops_tariff_panel()


# ═══════════════════════════════════════════════════════════════
# PAGE — RIDERS UPLOAD (standalone)
# ═══════════════════════════════════════════════════════════════
elif st.session_state["page"] == "op_riders":
    render_ops_riders_panel()


# ═══════════════════════════════════════════════════════════════
# PAGE — PAST USAGE (recalculate + export on one screen)
# ═══════════════════════════════════════════════════════════════
elif st.session_state["page"] == "op_past":
    render_past_usage_bills_page()


# ═══════════════════════════════════════════════════════════════
# PAGE 2 — RESULTS
# ═══════════════════════════════════════════════════════════════
elif st.session_state["page"] == "results":
    # Load data
    usage_df: pd.DataFrame = st.session_state.get("usage_df")
    profile: dict = st.session_state.get("profile", {})
    pdf_name: str = st.session_state.get("pdf_name", "Unknown file")

    if usage_df is None:
        st.session_state["page"] = "upload"
        st.rerun()

    usage_df = usage_df.copy()
    usage_df["bill_period_end"] = pd.to_datetime(usage_df["bill_period_end"], errors="coerce")
    usage_df = usage_df.dropna(subset=["bill_period_end"])

    if usage_df.empty:
        st.error("No valid billing records were extracted from the PDF.")
        st.caption("Try another bill file, or use **Back to upload**.")
        if st.button("Back to upload"):
            st.session_state["page"] = "upload"
            st.session_state["usage_df"] = None
            st.session_state["usage_bills_pdf_batch_key"] = None
            st.rerun()
        st.stop()

    contract_id = str(usage_df["contract_account"].iloc[0])
    customer_name = str(usage_df["customer"].iloc[0])

    render_usage_results_header(
        source_label=pdf_name,
        customer_name=customer_name,
        contract_id=contract_id,
        back_button_key="results_nav_back_upload",
    )

    render_anomaly_detection_settings_expander()
    analysis_tab1, analysis_tab2, analysis_tab3 = st.tabs(["Account", "Rate compare", "Schedule compare"])

    with analysis_tab1:
        render_account_usage_charges_section(
            usage_df,
            profile=profile,
            widget_key_prefix="",
            show_profile_section=True,
        )

    with analysis_tab2:
        render_rate_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")

    with analysis_tab3:
        render_schedule_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")


else:
    st.session_state["page"] = "upload"
    st.rerun()
