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


# Baseweb menus render in a body portal; Streamlit emotion sheets often beat in-app <style> tags.
_TB_DARK_BASEWEB_MENU_CSS = """
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="menu"],
[data-baseweb="menu"] > div {
    background-color: #141414 !important;
    color: #f5f5f5 !important;
    border-color: #404040 !important;
}
[data-baseweb="popover"] li,
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="menu"] li,
[data-baseweb="menu"] [role="option"],
[data-baseweb="menu"] ul {
    color: #f5f5f5 !important;
    background-color: #141414 !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover {
    background-color: #262626 !important;
}
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background-color: #0a0a0a !important;
    border-color: #404040 !important;
    color: #f5f5f5 !important;
}
"""

_TB_LIGHT_BASEWEB_MENU_CSS = """
:root { color-scheme: light !important; }
html body div[data-baseweb="popover"],
html body div[data-baseweb="popover"] > div,
html body div[data-baseweb="popover"] > div > div,
html body ul[data-baseweb="menu"],
html body ul[data-baseweb="menu"] > div,
html body div[data-baseweb="popover"] ul,
html body div[data-baseweb="popover"] li,
html body div[data-baseweb="popover"] [role="listbox"],
html body div[data-baseweb="popover"] [role="presentation"],
html body div[data-baseweb="popover"] [role="option"],
html body div[data-baseweb="popover"] [aria-disabled="true"],
html body div[data-baseweb="popover"] [class*="st-emotion-cache"],
html body ul[data-baseweb="menu"] [class*="st-emotion-cache"] {
    background-color: #ffffff !important;
    background: #ffffff !important;
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
    border-color: #d4ccc0 !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1) !important;
}
html body div[data-baseweb="popover"] li:hover,
html body div[data-baseweb="popover"] [role="option"]:hover,
html body ul[data-baseweb="menu"] li:hover {
    background-color: #f0ebe3 !important;
    color: #0a0a0a !important;
}
html body div[data-baseweb="popover"] span,
html body div[data-baseweb="popover"] p {
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background-color: #ffffff !important;
    border: 1px solid #d4ccc0 !important;
    color: #0a0a0a !important;
}
[data-testid="stMultiSelect"] [data-baseweb="select"] input {
    background-color: transparent !important;
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
"""


def _inject_baseweb_menu_css() -> None:
    """Event-container styles load after Streamlit emotion theme (fixes dark 'No results' panel)."""
    css = (
        _TB_LIGHT_BASEWEB_MENU_CSS
        if st.session_state.get("ui_theme") == "Light"
        else ""
    )
    st.html(f"<style id='tb-baseweb-menus'>{css}</style>")


def _select_persisted_tab(labels: list[str], session_key: str) -> str:
    """Section picker that keeps the active tab across reruns (e.g. theme toggle)."""
    if session_key not in st.session_state or st.session_state[session_key] not in labels:
        st.session_state[session_key] = labels[0]
    selected = st.segmented_control(
        "Section",
        options=labels,
        default=st.session_state[session_key],
        key=session_key,
        label_visibility="collapsed",
        width="stretch",
    )
    return selected if selected is not None else st.session_state[session_key]


# ---------------------------------------------------
# Page config & global CSS
# ---------------------------------------------------
if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "Dark"

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

/* Persisted analysis sections (segmented control; survives theme toggle) */
[data-testid="stButtonGroup"] {
    width: 100% !important;
    margin-bottom: 0.8rem !important;
}
[data-testid="stButtonGroup"] > div {
    display: flex !important;
    width: 100% !important;
    gap: 0.2rem !important;
    background: #0a0a0a !important;
    border: 1px solid #333333 !important;
    border-radius: 12px !important;
    padding: 0.25rem !important;
    box-shadow: none !important;
}
[data-testid="stButtonGroup"] button {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    font-size: 0.86rem !important;
    font-weight: 600 !important;
    color: #a3a3a3 !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
[data-testid="stButtonGroup"] button[aria-pressed="true"] {
    color: #ffffff !important;
    background: #262626 !important;
    border-color: #525252 !important;
}
[data-testid="stButtonGroup"] button:hover:not([aria-pressed="true"]) {
    color: #ffffff !important;
    background: #171717 !important;
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

/* Unified buttons (dark theme): shared shape; primary = filled light; secondary/download = outline */
[data-testid="stButton"] > button,
[data-testid="stDownloadButton"] > button,
[data-testid="stFileUploaderDropzone"] button {
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    padding: 0.35rem 0.9rem !important;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease !important;
}

[data-testid="stButton"] > button[kind="secondary"],
[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    color: #e5e5e5 !important;
    border: 1px solid #404040 !important;
    -webkit-text-fill-color: #e5e5e5 !important;
}
[data-testid="stButton"] > button[kind="secondary"] *,
[data-testid="stDownloadButton"] > button * {
    color: #e5e5e5 !important;
    -webkit-text-fill-color: #e5e5e5 !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover,
[data-testid="stDownloadButton"] > button:hover {
    background: #141414 !important;
    border-color: #737373 !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover *,
[data-testid="stDownloadButton"] > button:hover * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stButton"] > button[kind="secondary"]:focus-visible,
[data-testid="stDownloadButton"] > button:focus-visible {
    box-shadow: 0 0 0 2px #525252 !important;
}

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
    -webkit-text-fill-color: #000000 !important;
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

[data-testid="stFileUploaderDropzone"] button {
    background: #f0f0f0 !important;
    color: #0a0a0a !important;
    border: 1px solid #d4d4d4 !important;
    -webkit-text-fill-color: #0a0a0a !important;
    margin-top: 0.4rem;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: #ffffff !important;
    border-color: #e5e5e5 !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}

/* Sidebar nav uses default (secondary) buttons — same outline/fill rules as main */
section[data-testid="stSidebar"] [data-testid="stButton"] > button[kind="secondary"] {
    width: 100%;
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

.main a, [data-testid="stMarkdownContainer"] a { color: #93c5fd !important; }

[data-testid="stExpander"] [data-testid="stVerticalBlock"] p,
[data-testid="stExpander"] [data-testid="stVerticalBlock"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #e8e8e8 !important;
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

/* Charts: hide Vega-Embed "..." menu; Streamlit toolbar provides Fullscreen */
.vega-embed details,
.vega-embed.has-actions details,
.vega-embed .vega-actions,
.vega-embed.has-actions .vega-actions {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
    height: 0 !important;
    width: 0 !important;
    overflow: hidden !important;
    opacity: 0 !important;
}
/* Chart toolbar: Streamlit native icons (do not override SVG). Fullscreen only. */
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) {
    opacity: 1 !important;
    top: -2.65rem !important;
    pointer-events: auto !important;
    z-index: 20 !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"]:has(button[aria-label="Show data"]),
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"]:has(button[aria-label="Show chart"]) {
    display: none !important;
}
/* Dark theme: chart toolbar tray + fullscreen button (single border on tray only) */
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonContainer"] {
    background: #262626 !important;
    color: #e5e5e5 !important;
    border: 1px solid #525252 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35) !important;
    padding: 0 !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"],
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"] button {
    background: transparent !important;
    color: #e5e5e5 !important;
    border: none !important;
    outline: none !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonContainer"]:hover {
    background: #333333 !important;
    border-color: #737373 !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"] button:hover {
    background: transparent !important;
    border: none !important;
    color: #ffffff !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"] button,
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"],
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"] svg,
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"] svg * {
    -webkit-text-fill-color: unset !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"] svg {
    display: block !important;
    width: 1.25rem !important;
    height: 1.25rem !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"] svg path {
    fill: none !important;
    stroke: currentColor !important;
    vector-effect: non-scaling-stroke;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonIcon"] svg rect {
    fill: none !important;
    stroke: none !important;
}

</style>
""", unsafe_allow_html=True)

if st.session_state.get("ui_theme") == "Dark":
    st.markdown(
        f"<style id='tb-dark-baseweb-menus'>{_TB_DARK_BASEWEB_MENU_CSS}</style>",
        unsafe_allow_html=True,
    )

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
    if st.session_state.get("ui_theme") == "Light" and isinstance(df, pd.DataFrame):
        _render_light_table(df)
        return
    if isinstance(df, pd.DataFrame):
        colors = theme_palette()
        styled = (
            df.style
            .set_properties(
                **{
                    "background-color": colors["table_bg"],
                    "color": colors["table_text"],
                    "border-color": colors["table_border"],
                }
            )
            .set_table_styles(
                [
                    {
                        "selector": "th",
                        "props": [
                            ("background-color", colors["table_header_bg"]),
                            ("color", colors["table_text"]),
                            ("border-color", colors["table_border"]),
                        ],
                    }
                ]
            )
        )
        st.dataframe(styled, **kwargs)
    else:
        st.dataframe(df, **kwargs)


def _format_table_value(value) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (float, np.floating)):
        return f"{float(value):,.2f}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return str(value)


def _render_light_table(df: pd.DataFrame) -> None:
    colors = theme_palette()
    d = df.copy()
    max_rows = 500
    clipped = len(d) > max_rows
    if clipped:
        d = d.head(max_rows)
    table_id = f"tb_{abs(hash(tuple(map(str, d.columns))))}_{len(d)}"
    header = "".join(f"<th>{str(col)}</th>" for col in d.columns)
    rows = []
    for _, row in d.iterrows():
        cells = "".join(f"<td>{_format_table_value(row[col])}</td>" for col in d.columns)
        rows.append(f"<tr>{cells}</tr>")
    html = f"""
<style>
#{table_id}_wrap {{
  max-height: 460px;
  overflow: auto;
  border: 1px solid {colors["table_border"]};
  border-radius: 10px;
  background: {colors["table_bg"]};
}}
#{table_id} {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}}
#{table_id} th {{
  position: sticky;
  top: 0;
  z-index: 1;
  background: {colors["table_header_bg"]};
  color: {colors["table_text"]};
  border: 1px solid {colors["table_border"]};
  padding: 0.65rem 0.75rem;
  text-align: left;
  font-weight: 700;
}}
#{table_id} td {{
  background: {colors["table_bg"]};
  color: {colors["table_text"]};
  border: 1px solid {colors["table_border"]};
  padding: 0.58rem 0.75rem;
}}
#{table_id} tr:nth-child(even) td {{
  background: {colors["table_alt_bg"]};
}}
</style>
<div id="{table_id}_wrap">
  <table id="{table_id}">
    <thead><tr>{header}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    if clipped:
        st.caption(f"Showing first {max_rows:,} rows.")


def theme_palette() -> dict:
    if st.session_state.get("ui_theme") == "Light":
        return {
            "chart_bg": "#faf8f5",
            "chart_stroke": "#d4ccc0",
            "axis_label": "#525252",
            "axis_title": "#111111",
            "grid": "#ded6cc",
            "usage_color": "#2563eb",
            "charge_color": "#475569",
            "table_bg": "#ffffff",
            "table_alt_bg": "#f7f3ed",
            "table_header_bg": "#e6ded2",
            "table_text": "#111111",
            "table_border": "#8f8578",
        }
    return {
        "chart_bg": "#0a0a0a",
        "chart_stroke": "#333333",
        "axis_label": "#a3a3a3",
        "axis_title": "#e5e5e5",
        "grid": "#333333",
        "usage_color": "#7cc7ff",
        "charge_color": "#9ca3af",
        "table_bg": "#0f131a",
        "table_alt_bg": "#111722",
        "table_header_bg": "#181b23",
        "table_text": "#f5f5f5",
        "table_border": "#333333",
    }


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


def _billing_days_by_account(s: pd.Series) -> pd.Series:
    d = s.diff().dt.days.astype(float)
    med = d.median()
    if pd.isna(med) or float(med) < 1:
        med = 30.0
    return d.fillna(med).clip(lower=1)


def _local_anomalies_export_table(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Local fallback when the running backend does not yet expose POST /api/anomalies."""
    df = _strip_total_and_parse_dates(usage_full_history)
    if df.empty:
        return pd.DataFrame()

    p = anomaly_params_from_session()
    if "contract_account" in df.columns:
        df["account"] = df["contract_account"].astype(str).str.strip()
    elif "account_number" in df.columns:
        df["account"] = df["account_number"].astype(str).str.strip()
    else:
        df["account"] = "Single_Account"

    for col in ("usage_kwh", "charges"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else np.nan
    df = df.dropna(subset=["usage_kwh"])
    df = df[df["usage_kwh"] >= 0].copy()
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["account", "bill_period_end"]).reset_index(drop=True)
    df["billing_days"] = df.groupby("account", group_keys=False)["bill_period_end"].transform(
        _billing_days_by_account
    )
    df["daily_kwh"] = np.where(df["billing_days"] > 0, df["usage_kwh"] / df["billing_days"], np.nan)
    df["month"] = df["bill_period_end"].dt.month
    df["same_month_median_daily_kwh"] = df.groupby(["account", "month"])["daily_kwh"].transform("median")
    usage_delta = df["daily_kwh"] - df["same_month_median_daily_kwh"]
    usage_ratio = np.where(
        df["same_month_median_daily_kwh"] > 0,
        usage_delta / df["same_month_median_daily_kwh"],
        0.0,
    )
    df["usage_spike"] = (
        (df.groupby(["account", "month"])["daily_kwh"].transform("count") > 1)
        & (usage_ratio >= float(p["pct_spike_limit"]))
        & (usage_delta >= float(p["abs_spike_limit"]))
    )
    first_seen = df.groupby("account")["bill_period_end"].transform("min")
    df["new_activation"] = df["bill_period_end"].eq(first_seen)

    df["$/kWh"] = np.where(df["usage_kwh"] > 0, df["charges"] / df["usage_kwh"], np.nan)
    med_cpk = df.groupby("account")["$/kWh"].transform("median")
    df["billing_outlier"] = (
        (df["usage_kwh"] >= float(p["billing_min_kwh"]))
        & med_cpk.notna()
        & (med_cpk > 0)
        & (df["$/kWh"] > (med_cpk * float(p["billing_median_multiplier"])))
        & (df["$/kWh"] > med_cpk + float(p["billing_min_delta_cpk"]))
    )
    med_charge = df.groupby("account")["charges"].transform("median")
    df["charge_spike"] = (
        (df["charges"] >= float(p["charge_min_usd"]))
        & med_charge.notna()
        & (med_charge > 0)
        & (df["charges"] > float(p["charge_median_multiplier"]) * med_charge)
    )

    mask = df["usage_spike"] | df["new_activation"] | df["billing_outlier"] | df["charge_spike"]
    out = df.loc[mask].copy()
    if out.empty:
        return pd.DataFrame()

    def _notes(row):
        parts = []
        if bool(row.get("usage_spike")):
            normal = row.get("same_month_median_daily_kwh")
            current = row.get("daily_kwh")
            if pd.notna(normal) and normal > 0 and pd.notna(current):
                pct = ((current - normal) / normal) * 100
                parts.append(f"Spike of {pct:.1f}%. Current usage is {current:.1f} kWh/day vs historical normal of {normal:.1f} kWh/day.")
            else:
                parts.append("Usage is unusually high for this account.")
        if bool(row.get("new_activation")):
            parts.append("New activation or first bill in available history.")
        if bool(row.get("billing_outlier")) and pd.notna(row.get("$/kWh")):
            parts.append(f"Billing: ${row['$/kWh']:.4f}/kWh vs typical median ${med_cpk.loc[row.name]:.4f}/kWh for this account.")
        if bool(row.get("charge_spike")) and pd.notna(row.get("charges")):
            parts.append(f"Charge: ${row['charges']:,.2f} vs typical median bill ${med_charge.loc[row.name]:,.2f}.")
        return " ".join(parts).strip()

    out["notes"] = out.apply(_notes, axis=1)
    if view_period_df is not None and not view_period_df.empty:
        vp = _strip_total_and_parse_dates(view_period_df)
        if not vp.empty:
            out = out[(out["bill_period_end"] >= vp["bill_period_end"].min()) & (out["bill_period_end"] <= vp["bill_period_end"].max())]

    if out.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "bill_period_end": out["bill_period_end"].dt.strftime("%Y-%m-%d"),
            "account": out["account"].astype(str),
            "usage_kwh": out["usage_kwh"],
            "charges": out["charges"],
            "$/kWh": pd.to_numeric(out["$/kWh"], errors="coerce").round(4),
            "usage_spike": out["usage_spike"],
            "new_activation": out["new_activation"],
            "billing_outlier": out["billing_outlier"],
            "charge_spike": out["charge_spike"],
            "notes": out["notes"],
        }
    ).reset_index(drop=True)


def build_anomalies_export_table(
    usage_full_history: pd.DataFrame,
    *,
    view_period_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Same grid as the Anomalies table / Excel download (for multi-sheet workbooks)."""
    pe = _strip_total_and_parse_dates(usage_full_history)
    if pe.empty:
        return pd.DataFrame()
    p = anomaly_params_from_session()
    payload = {
        "usage_records": _usage_records_for_api(pe),
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
            payload["view_records"] = _usage_records_for_api(vp)
    try:
        r = requests.post(f"{BACKEND_URL}/api/anomalies", json=payload, timeout=600)
        if r.status_code == 404:
            return _local_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        return _local_anomalies_export_table(usage_full_history, view_period_df=view_period_df)
    except requests.exceptions.HTTPError:
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = (getattr(r, "text", None) or "").strip()
        raise RuntimeError(f"{r.status_code} {r.reason}" + (f" — {detail}" if detail else "")) from None
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
    _st_dataframe(disp, width="stretch", hide_index=True, column_config=cfg)
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
                "ACCOUNT NO.", "Account Profile", "Phone Number", "Mailing Address",
                "Service Address", "Customer Class", "Turn On Date",
                "District Office", "Meter Number(s)", "Current Rate",
                "Tax District", "NAICS Code", "Voltage", "Delivery Phase",
                "Minimum Demand", "Facility Charge", "Billing Status", "Key Account Manager",
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
        _gcol, _toggle_col, _tcol = st.columns([0.44, 0.12, 0.44], gap="small")
        with _gcol:
            st.markdown(
                '<div style="text-align:right; padding-top:0.42rem; font-weight:700;">Graph</div>',
                unsafe_allow_html=True,
            )
        with _toggle_col:
            if hasattr(st, "toggle"):
                _table_only = st.toggle(
                    "Graph or table",
                    value=False,
                    key=_ktoggle,
                    help="Off: monthly charts. On: billing records table.",
                    label_visibility="collapsed",
                )
            else:
                _table_only = st.checkbox(
                    "Graph or table",
                    value=False,
                    key=_ktoggle,
                    help="Off: monthly charts. On: billing records table.",
                    label_visibility="collapsed",
                )
        with _tcol:
            st.markdown(
                '<div style="text-align:left; padding-top:0.42rem; font-weight:700;">Table</div>',
                unsafe_allow_html=True,
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
                    colors = theme_palette()
                    return (
                        chart.properties(
                            height=320 if _n_months > 18 else 280,
                            usermeta={"embedOptions": {"actions": False}},
                        )
                        .configure(background=colors["chart_bg"])
                        .configure_view(stroke=colors["chart_stroke"])
                        .configure_axis(
                            labelColor=colors["axis_label"],
                            titleColor=colors["axis_title"],
                            gridColor=colors["grid"],
                            domainColor=colors["chart_stroke"],
                        )
                    )

                _colors = theme_palette()
                with c_left:
                    st.markdown("**Usage (kWh) by month**")
                    ch_u = _usage_charges_theme(
                        alt.Chart(chart_df)
                        .mark_area(line=True, color=_colors["usage_color"], interpolate="monotone", opacity=0.68)
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
                        .mark_area(line=True, color=_colors["charge_color"], interpolate="monotone", opacity=0.68)
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
        if chart_df.empty:
            st.info("No monthly billing rows.")
        else:
            c_left, c_right = st.columns(2, gap="medium")
            table_monthly = chart_df.copy()
            table_monthly["bill_period_end"] = pd.to_datetime(
                table_monthly["bill_period_end"], errors="coerce"
            ).dt.strftime("%Y-%m")
            with c_left:
                st.markdown("**Usage (kWh) by month**")
                usage_table = table_monthly[["bill_period_end", "Usage (kWh)"]].rename(
                    columns={"bill_period_end": "Month"}
                )
                _st_dataframe(
                    usage_table,
                    width="stretch",
                    height=420,
                    hide_index=True,
                    column_config={
                        "Month": st.column_config.TextColumn("Month"),
                        "Usage (kWh)": st.column_config.NumberColumn("Usage (kWh)", format="%.0f"),
                    },
                    key=f"{widget_key_prefix}usage_monthly_table",
                )
            with c_right:
                st.markdown("**Charges ($) by month**")
                charges_table = table_monthly[["bill_period_end", "Charges ($)"]].rename(
                    columns={"bill_period_end": "Month"}
                )
                _st_dataframe(
                    charges_table,
                    width="stretch",
                    height=420,
                    hide_index=True,
                    column_config={
                        "Month": st.column_config.TextColumn("Month"),
                        "Charges ($)": st.column_config.NumberColumn("Charges ($)", format="$%.2f"),
                    },
                    key=f"{widget_key_prefix}charges_monthly_table",
                )

        if not disp.empty:
            st.markdown('<div class="section-title">All Billing Records</div>', unsafe_allow_html=True)
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
                _st_dataframe(
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
            _st_dataframe(gsd, width="stretch", height=460, hide_index=True, column_config=gap_cfg)
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


def _session_uploaded_bill_options() -> pd.DataFrame:
    rows = st.session_state.get("uploaded_bill_options_session", [])
    cols = [
        "batch_id",
        "source_pdf",
        "account_number",
        "customer_name",
        "bill_year",
        "uploaded_at",
        "row_count",
        "_session_only",
    ]
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows)
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    out["uploaded_at"] = pd.to_datetime(out["uploaded_at"], errors="coerce")
    out["_session_only"] = out["_session_only"].fillna(True)
    return out[cols]


def _remember_uploaded_bill_payload(payload: dict, usage_df: pd.DataFrame, source_pdf: str) -> None:
    if usage_df is None or usage_df.empty:
        return
    batch_id = str(payload.get("batch_id", "") or "").strip()
    if not batch_id:
        return
    acct = str(payload.get("account_number", "") or "").strip()
    name = str(payload.get("account_name", "") or "").strip()
    if not acct and "contract_account" in usage_df.columns and not usage_df["contract_account"].dropna().empty:
        acct = str(usage_df["contract_account"].dropna().iloc[0]).strip()
    if not name and "customer" in usage_df.columns and not usage_df["customer"].dropna().empty:
        name = str(usage_df["customer"].dropna().iloc[0]).strip()
    if not acct:
        return

    d = usage_df.copy()
    d["bill_period_end"] = pd.to_datetime(d.get("bill_period_end"), errors="coerce")
    d = d.dropna(subset=["bill_period_end"])
    uploaded_at = pd.Timestamp.now().isoformat()
    year_counts = d["bill_period_end"].dt.year.astype(str).value_counts().to_dict()

    option_rows = st.session_state.get("uploaded_bill_options_session", [])
    option_rows = [
        r for r in option_rows
        if not (str(r.get("batch_id", "")).strip() == batch_id)
    ]
    for year, count in sorted(year_counts.items()):
        option_rows.append(
            {
                "batch_id": batch_id,
                "source_pdf": source_pdf,
                "account_number": acct,
                "customer_name": name or "Unknown Customer",
                "bill_year": str(year),
                "uploaded_at": uploaded_at,
                "row_count": int(count),
                "_session_only": True,
            }
        )
    st.session_state["uploaded_bill_options_session"] = option_rows

    records_cache = st.session_state.get("uploaded_usage_records_session", {})
    records_cache[batch_id] = {
        "account_number": acct,
        "records": _usage_records_for_api(d),
        "profile": payload.get("profile") or {},
    }
    st.session_state["uploaded_usage_records_session"] = records_cache


def _session_usage_records_for_batches(batches_to_load: pd.DataFrame) -> list[dict] | None:
    cache = st.session_state.get("uploaded_usage_records_session", {})
    if not cache or batches_to_load is None or batches_to_load.empty:
        return None
    records: list[dict] = []
    seen: set[str] = set()
    for _, row in batches_to_load.iterrows():
        bid = str(row.get("batch_id", "") or "").strip()
        if not bid or bid in seen or bid not in cache:
            continue
        seen.add(bid)
        records.extend(cache[bid].get("records") or [])
    return records or None


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_uploaded_bill_options_api(backend_base: str) -> tuple[dict, ...]:
    """Persisted bill list from the API (SQLite via backend). Survives page refresh."""
    r = requests.get(f"{backend_base}/api/bills", timeout=120)
    r.raise_for_status()
    payload = r.json()
    return tuple(payload) if isinstance(payload, list) else tuple()


def fetch_uploaded_bill_options() -> pd.DataFrame:
    _cols = [
        "batch_id",
        "source_pdf",
        "account_number",
        "customer_name",
        "bill_year",
        "uploaded_at",
        "row_count",
    ]
    try:
        rows = list(_fetch_uploaded_bill_options_api(BACKEND_URL))
    except requests.exceptions.RequestException as exc:
        rows = []
        if not _session_uploaded_bill_options().empty:
            st.warning(
                f"Could not refresh saved bills from the server ({exc}). "
                "Showing bills uploaded in this browser session only."
            )
        else:
            st.warning(
                f"Could not load saved bills from the server ({exc}). "
                "Start the backend API, then refresh this page."
            )
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
    api_df = pd.DataFrame(norm, columns=_cols)
    session_df = _session_uploaded_bill_options()
    out = pd.concat([api_df, session_df[_cols]], ignore_index=True)
    if not out.empty:
        out["account_number"] = out["account_number"].astype(str).str.strip()
        out["customer_name"] = out["customer_name"].astype(str).str.strip()
        out["bill_year"] = out["bill_year"].astype(str)
        out["uploaded_at"] = pd.to_datetime(out["uploaded_at"], errors="coerce")
        out = out[
            ~(
                out["account_number"].str.upper().eq("TEST")
                & out["customer_name"].str.upper().str.contains("TEST", na=False)
            )
        ].reset_index(drop=True)
        out = out.drop_duplicates(
            subset=["batch_id", "account_number", "customer_name", "bill_year"],
            keep="first",
        ).reset_index(drop=True)
    return out


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


def fetch_saved_bill_profile(account_number: str, batch_ids: list[str] | None = None) -> dict:
    cache = st.session_state.get("uploaded_usage_records_session", {})
    if batch_ids:
        for bid in batch_ids:
            cached = cache.get(str(bid).strip()) or {}
            prof = cached.get("profile") or {}
            if isinstance(prof, dict) and prof:
                return prof
    params = {"account_number": str(account_number).strip()}
    if batch_ids:
        params["batch_ids"] = ",".join(str(x).strip() for x in batch_ids if str(x).strip())
    try:
        r = requests.get(f"{BACKEND_URL}/api/bills/profile", params=params, timeout=60)
        if r.status_code != 200:
            return {}
        data = r.json() or {}
        prof = data.get("profile") or {}
        return prof if isinstance(prof, dict) else {}
    except Exception:
        return {}


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
            display_all.assign(
                _uploaded_sort=pd.to_datetime(display_all["uploaded_at"], errors="coerce"),
                _account_sort=display_all["account_number"].astype(str).str.strip(),
                _customer_sort=display_all["customer_name"].astype(str).str.strip(),
            )
            .groupby(["account_number", "customer_name"], as_index=False, dropna=False)
            .agg(
                uploaded_at=("_uploaded_sort", "max"),
                _account_sort=("_account_sort", "first"),
                _customer_sort=("_customer_sort", "first"),
            )
            .sort_values(["uploaded_at", "_account_sort", "_customer_sort"], ascending=[False, True, True], na_position="last")
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
            f"Loaded {len(acct_labels)} saved account(s). Open the dropdown to search by number or name."
        )

        acct_row = acct_choices.loc[acct_choices["acct_label"] == selected_label].iloc[0]

        for_account = display_all[
            (display_all["account_number"].astype(str).str.strip() == str(acct_row["account_number"]).strip())
            & (display_all["customer_name"].astype(str).str.strip() == str(acct_row["customer_name"]).strip())
        ]
        selected_period = "All Years"

        batches_to_load: pd.DataFrame | None = None
        selected_row: pd.Series | None = None

        if selected_period in ("All Years", "Last 12 Months"):
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
                selected_schedule_ids = sorted(_schedule_options(BACKEND_URL))
            except Exception:
                selected_schedule_ids = ["100", "102", "110", "120", "154"]
            tariff_kind, tariff_payload = "file", None
            rider_kind, rider_payload = "file", None

            if st.button("Run recalculation", type="primary", key=f"{key_prefix}recalc_all_btn"):
                if not selected_schedule_ids:
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
                            session_usage_records = _session_usage_records_for_batches(batches_to_load)
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
                                "schedule_ids": list(selected_schedule_ids),
                                "tariff_source": tariff_api_source,
                                "tariff_version": tariff_api_version,
                                "rider_source": rider_api_source,
                                "rider_version": rider_api_version,
                                **period_kw,
                            }
                            if session_usage_records is not None:
                                body["usage_records"] = session_usage_records
                            else:
                                body["account_number"] = str(selected_row["account_number"]).strip()
                                body["batches"] = batches_pl
                            r = _api_request("post", "/api/calculate", json=body)
                            recalc_result = pd.DataFrame(r.json()["records"])

                            st.session_state[result_df_key] = recalc_result
                            st.session_state[schedule_ids_key] = list(selected_schedule_ids)
                            batch_ids_for_profile = [
                                str(x.get("batch_id", "")).strip()
                                for _, x in batches_to_load.iterrows()
                                if str(x.get("batch_id", "")).strip()
                            ]
                            st.session_state[f"{key_prefix}recalc_profile"] = fetch_saved_bill_profile(
                                str(selected_row["account_number"]).strip(),
                                batch_ids_for_profile,
                            )
                            st.session_state[f"{key_prefix}recalc_source_label"] = (
                                f"Past usage · {period_hist} · "
                                f"{int(len(batches_to_load))} saved row group(s)"
                            )
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
                            st.session_state["page"] = "op_past_results"
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Recalculation failed: {exc}")


def _recalc_available_schedules(result_df: pd.DataFrame, schedule_ids: list | None = None) -> list[str]:
    found = []
    for col in result_df.columns:
        m = re.match(r"^ve(\d+)_calculated_amount$", str(col))
        if m:
            found.append(m.group(1))
    if schedule_ids:
        wanted = [str(s) for s in schedule_ids]
        found = [s for s in wanted if s in found]
    return sorted(set(found), key=lambda x: int(x) if str(x).isdigit() else str(x))


def _recalc_filter_by_year(result_df: pd.DataFrame, selected_year) -> tuple[pd.DataFrame, str]:
    df = result_df.copy()
    df["bill_period_end"] = pd.to_datetime(df["bill_period_end"], errors="coerce")
    df = df.dropna(subset=["bill_period_end"])
    return filter_by_year_option(df, selected_year)


def render_recalc_rate_compare_tab(
    result_df: pd.DataFrame,
    *,
    contract_id: str,
    schedule_ids: list | None = None,
    widget_key_prefix: str = "pastusage_recalc_like_",
) -> None:
    schedules = _recalc_available_schedules(result_df, schedule_ids)
    if not schedules:
        st.info("No calculated schedule columns are available in this recalculation result.")
        return
    kp = widget_key_prefix
    available_years = build_year_options(result_df)
    c_year, c_sched, _sp = st.columns([1, 1, 3])
    with c_year:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}rc_year")
    with c_sched:
        schedule_id = st.selectbox("Schedule", schedules, key=f"{kp}rc_schedule")

    df_year, year_label = _recalc_filter_by_year(result_df, selected_year)
    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
        return

    calc_col = f"ve{schedule_id}_calculated_amount"
    actual_total = pd.to_numeric(df_year.get("charges", 0), errors="coerce").fillna(0).sum()
    calc_total = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce").fillna(0).sum()
    total_savings = actual_total - calc_total
    savings_cls = "kpi-positive" if total_savings >= 0 else "kpi-negative"
    savings_label = "Total Savings" if total_savings >= 0 else "Total Overpaid"
    st.markdown(
        '<div class="kpi-row compare-kpi-band">'
        + kpi_card(f"Actual Charges ({year_label})", f"${actual_total:,.2f}")
        + kpi_card(f"VE-{schedule_id} Calculated", f"${calc_total:,.2f}")
        + kpi_card(savings_label, f"${abs(total_savings):,.2f}", cls=savings_cls)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Detailed Comparison</div>', unsafe_allow_html=True)
    sched_cols = [
        c for c in df_year.columns
        if str(c).startswith(f"ve{schedule_id}_") and "case_type" not in str(c).lower()
    ]
    base_cols = [
        c for c in ["bill_period_end", "current_rate", "usage_kwh", "demand_kw", "charges"]
        if c in df_year.columns
    ]
    detailed = df_year[base_cols + sched_cols].copy()
    detailed = reorder_first(add_total(detailed))
    safe_year = re.sub(r"[^\w]+", "_", str(year_label))[:32]
    render_dataframe_with_fixed_total(
        detailed,
        period_col="bill_period_end",
        column_config=merged_comparison_column_config(detailed),
        key_prefix=f"{kp}rc_full_{schedule_id}_{safe_year}",
    )
    st.download_button(
        "Download full detail (Excel)",
        data=export_excel(detailed),
        file_name=f"{contract_id}_VE{schedule_id}_{year_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{kp}dl_full_rc_{schedule_id}_{safe_year}",
    )
    monthly = monthly_calculated_view_df(detailed)
    st.markdown('<div class="section-title">Monthly summary</div>', unsafe_allow_html=True)
    render_dataframe_with_fixed_total(
        monthly,
        period_col="bill_period_end",
        column_config=monthly_view_column_config(monthly),
        key_prefix=f"{kp}rc_sum_{schedule_id}_{safe_year}",
    )
    render_anomalies_section(
        result_df,
        view_period_df=df_year,
        title=f"Anomalies — {year_label}",
        key_suffix=f"{kp}rc_{schedule_id}_{safe_year}",
    )


def render_recalc_schedule_compare_tab(
    result_df: pd.DataFrame,
    *,
    contract_id: str,
    schedule_ids: list | None = None,
    widget_key_prefix: str = "pastusage_recalc_like_",
) -> None:
    schedules = _recalc_available_schedules(result_df, schedule_ids)
    if not schedules:
        st.info("No calculated schedule columns are available in this recalculation result.")
        return
    kp = widget_key_prefix
    available_years = build_year_options(result_df)
    c_year, c_sched = st.columns([1, 2])
    with c_year:
        selected_year = st.selectbox("Year", available_years, key=f"{kp}sc_year")
    with c_sched:
        selected_schedules = st.multiselect(
            "Schedules to Compare",
            options=schedules,
            default=schedules,
            key=f"{kp}sc_schedules",
        )
    if not selected_schedules:
        st.warning("Select at least one schedule to compare.")
        return

    df_year, year_label = _recalc_filter_by_year(result_df, selected_year)
    if df_year.empty:
        st.warning(f"No billing data found for {year_label}.")
        return

    actual_total = pd.to_numeric(df_year.get("charges", 0), errors="coerce").fillna(0).sum()
    comp_cols = [c for c in ["bill_period_end", "usage_kwh", "charges"] if c in df_year.columns]
    comp = df_year[comp_cols].copy()
    kpis = kpi_card("Actual Charges", f"${actual_total:,.2f}", year_label)
    for sid in selected_schedules:
        calc_col = f"ve{sid}_calculated_amount"
        calc_val = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce").fillna(0).sum()
        comp[f"VE-{sid} Calculated ($)"] = pd.to_numeric(df_year.get(calc_col, 0), errors="coerce")
        diff = actual_total - calc_val
        cls = "kpi-positive" if diff >= 0 else "kpi-negative"
        kpis += kpi_card(
            f"VE-{sid}",
            f"${calc_val:,.2f}",
            f"Save ${diff:,.2f}" if diff >= 0 else f"Over ${abs(diff):,.2f}",
            cls=cls,
        )
    st.markdown(f'<div class="kpi-row compare-kpi-band">{kpis}</div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Monthly calculated amounts</div>', unsafe_allow_html=True)
    result = reorder_first(add_total(comp))
    safe_year = re.sub(r"[^\w]+", "_", str(year_label))[:32]
    render_dataframe_with_fixed_total(
        result,
        period_col="bill_period_end",
        column_config=monthly_view_column_config(result),
        key_prefix=f"{kp}sc_monthly_{safe_year}",
    )
    base_name = f"{contract_id}_schedule_comparison_{safe_year}"
    st.download_button(
        "Download monthly summary (Excel)",
        data=export_excel(result),
        file_name=f"{base_name}_monthly_summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{kp}dl_sum_sc_{safe_year}",
    )
    render_anomalies_section(
        result_df,
        view_period_df=df_year,
        title=f"Anomalies — {year_label}",
        key_suffix=f"{kp}sc_{safe_year}",
    )


def render_recalc_results_like_upload(
    result_df: pd.DataFrame,
    *,
    result_name: str,
    profile: dict | None,
    source_label: str,
    schedule_ids: list | None,
    key_prefix: str,
) -> None:
    result_df = result_df.copy()
    result_df["bill_period_end"] = pd.to_datetime(result_df["bill_period_end"], errors="coerce")
    result_df = result_df.dropna(subset=["bill_period_end"])
    if result_df.empty:
        st.info("No results yet. Run **Run recalculation** first (pick account, period, sources, then run).")
        return
    contract_id = (
        str(result_df["contract_account"].dropna().iloc[0]).strip()
        if "contract_account" in result_df.columns and not result_df["contract_account"].dropna().empty
        else "Unknown account"
    )
    customer_name = (
        str(result_df["customer"].dropna().iloc[0]).strip()
        if "customer" in result_df.columns and not result_df["customer"].dropna().empty
        else "Unknown customer"
    )
    effective_profile = dict(profile or {})
    if not effective_profile:
        rate = (
            str(result_df["current_rate"].dropna().iloc[-1]).strip()
            if "current_rate" in result_df.columns and not result_df["current_rate"].dropna().empty
            else ""
        )
        first_bill = result_df["bill_period_end"].min().strftime("%Y-%m-%d")
        last_bill = result_df["bill_period_end"].max().strftime("%Y-%m-%d")
        effective_profile = {
            "ACCOUNT NO.": contract_id,
            "Account Profile": customer_name,
            "Current Rate": rate,
            "Billing Status": "Saved usage",
            "Turn On Date": f"{first_bill} to {last_bill}",
        }
    st.markdown('<div class="section-title">RECALCULATION RESULTS</div>', unsafe_allow_html=True)
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
        if st.button("Back to recalculation", type="secondary", key=f"{key_prefix}back_to_recalc"):
            st.session_state["page"] = "op_past"
            st.rerun()
    render_anomaly_detection_settings_expander()
    _past_tab_labels = ["Account", "Rate compare", "Schedule compare", "Downloads"]
    _past_tab = _select_persisted_tab(_past_tab_labels, f"{key_prefix}past_results_analysis_tab")
    if _past_tab == "Account":
        render_account_usage_charges_section(
            result_df,
            profile=effective_profile,
            widget_key_prefix=f"{key_prefix}acct_",
            show_profile_section=True,
        )
    elif _past_tab == "Rate compare":
        render_recalc_rate_compare_tab(
            result_df,
            contract_id=contract_id,
            schedule_ids=schedule_ids,
            widget_key_prefix=f"{key_prefix}rate_",
        )
    elif _past_tab == "Schedule compare":
        render_recalc_schedule_compare_tab(
            result_df,
            contract_id=contract_id,
            schedule_ids=schedule_ids,
            widget_key_prefix=f"{key_prefix}sched_",
        )
    elif _past_tab == "Downloads":
        summary = monthly_calculated_view_df(result_df)
        base_name = Path(result_name).stem
        try:
            anom = build_anomalies_export_table(result_df, view_period_df=result_df)
        except Exception:
            anom = pd.DataFrame()
        st.download_button(
            "Download monthly summary (Excel)",
            data=export_excel(summary),
            file_name=f"{base_name}_monthly_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_summary",
        )
        st.download_button(
            "Download full recalculation (Excel)",
            data=export_excel(result_df),
            file_name=result_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_full",
        )
        st.download_button(
            "Download one workbook (monthly + full + anomalies)",
            data=export_excel_multi_sheet(
                {
                    "Monthly_summary": summary,
                    "Full_recalculation": result_df,
                    "Anomalies": anom,
                }
            ),
            file_name=f"{base_name}_workbook_monthly_full_anomalies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}download_workbook",
        )


def render_ops_export_panel(
    *,
    key_prefix: str = "pastusage_",
    result_df_key: str = "pastusage_recalc_result_df",
    result_name_key: str = "pastusage_recalc_result_name",
    schedule_ids_key: str = "pastusage_recalc_schedule_ids",
    history_session_key: str = "pastusage_recalc_history",
    anomalies_key_suffix: str = "pastusage_export",
) -> None:
    result_df = st.session_state.get(result_df_key)
    result_name = st.session_state.get(result_name_key, "recalculation.xlsx")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        render_recalc_results_like_upload(
            result_df,
            result_name=result_name,
            profile=st.session_state.get(f"{key_prefix}recalc_profile", {}),
            source_label=st.session_state.get(f"{key_prefix}recalc_source_label", "Past usage recalculation"),
            schedule_ids=st.session_state.get(schedule_ids_key) or [],
            key_prefix=f"{key_prefix}recalc_results_",
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
        _st_dataframe(hist_df, width="stretch", hide_index=True)
        st.download_button(
            "Download run history (Excel)",
            data=export_excel(hist_df),
            file_name="recalc_run_history.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}recalc_history_download",
        )


def render_past_usage_bills_page() -> None:
    """Past usage recalculation form."""
    render_ops_recalc_panel()


def render_past_usage_results_page() -> None:
    """Dedicated results page for past usage recalculation."""
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
    if "ui_theme_selector" not in st.session_state:
        st.session_state["ui_theme_selector"] = st.session_state.get("ui_theme", "Dark")
    st.radio(
        "Theme",
        options=["Dark", "Light"],
        key="ui_theme_selector",
        horizontal=True,
    )
    st.session_state["ui_theme"] = st.session_state["ui_theme_selector"]
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
    _theme_override_markup = """
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
.kpi-value, .info-item-value {
    color: #000000 !important;
}
.hero-title, .results-nav-title {
    background: none !important;
    -webkit-text-fill-color: #000000 !important;
    color: #000000 !important;
    text-shadow: none !important;
    filter: none !important;
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

[data-testid="stButtonGroup"] > div {
    background: #f0ebe3 !important;
    border-color: #e8e0d6 !important;
}
[data-testid="stButtonGroup"] button {
    color: #404040 !important;
}
[data-testid="stButtonGroup"] button[aria-pressed="true"] {
    color: #000000 !important;
    background: #ffffff !important;
    border-color: #d4ccc0 !important;
}
[data-testid="stButtonGroup"] button:hover:not([aria-pressed="true"]) {
    color: #000000 !important;
    background: #ebe6de !important;
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
/* Light theme: same button system as dark (primary = light fill; secondary/download = outline) */
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
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):hover * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stButton"] > button[kind="primary"]:not(:disabled):not([disabled]):not([aria-disabled="true"]):focus-visible {
    box-shadow: 0 0 0 2px #a8a29e !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled,
[data-testid="stButton"] > button[kind="primary"][disabled],
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] {
    background: #e7e5e4 !important;
    color: #78716c !important;
    border-color: #d6d3d1 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #78716c !important;
}
[data-testid="stButton"] > button[kind="primary"]:disabled *,
[data-testid="stButton"] > button[kind="primary"][disabled] *,
[data-testid="stButton"] > button[kind="primary"][aria-disabled="true"] * {
    color: #78716c !important;
    -webkit-text-fill-color: #78716c !important;
}

[data-testid="stButton"] > button[kind="secondary"],
[data-testid="stDownloadButton"] > button {
    background: #ffffff !important;
    color: #0a0a0a !important;
    border: 1px solid #d4ccc0 !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stButton"] > button[kind="secondary"] *,
[data-testid="stDownloadButton"] > button * {
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover,
[data-testid="stDownloadButton"] > button:hover {
    background: #f0ebe3 !important;
    border-color: #a8a29e !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover *,
[data-testid="stDownloadButton"] > button:hover * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-testid="stButton"] > button[kind="secondary"]:focus-visible,
[data-testid="stDownloadButton"] > button:focus-visible {
    box-shadow: 0 0 0 2px #d4ccc0 !important;
}

[data-testid="stFileUploaderDropzone"] button {
    background: #f0f0f0 !important;
    color: #0a0a0a !important;
    border: 1px solid #d4d4d4 !important;
    -webkit-text-fill-color: #0a0a0a !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: #ffffff !important;
    border-color: #e5e5e5 !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid #e8e0d6 !important;
    border-radius: 10px !important;
}

.vega-embed details,
.vega-embed.has-actions details,
.vega-embed details[open],
.vega-embed.has-actions details[open],
.vega-embed details summary,
.vega-embed.has-actions details > summary,
.vega-embed .vega-actions,
.vega-embed.has-actions .vega-actions {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #d4ccc0 !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.12) !important;
}
.vega-embed details summary,
.vega-embed.has-actions details > summary {
    border-radius: 10px !important;
}
.vega-embed details summary:hover,
.vega-embed details summary:focus,
.vega-embed details summary:focus-visible,
.vega-embed.has-actions details > summary:hover,
.vega-embed.has-actions details > summary:focus,
.vega-embed.has-actions details > summary:focus-visible {
    background: #f2eee8 !important;
    color: #111111 !important;
    outline: 2px solid #d4ccc0 !important;
}
.vega-embed details summary::marker,
.vega-embed.has-actions details > summary::marker {
    color: #111111 !important;
}
.vega-embed details summary svg,
.vega-embed.has-actions details > summary svg,
.vega-embed .vega-actions svg,
.vega-embed.has-actions .vega-actions svg {
    color: #111111 !important;
    fill: #111111 !important;
    stroke: #111111 !important;
}
.vega-embed .vega-actions a,
.vega-embed.has-actions .vega-actions a {
    color: #111111 !important;
    background: #ffffff !important;
}
.vega-embed .vega-actions a:hover,
.vega-embed.has-actions .vega-actions a:hover {
    background: #f2eee8 !important;
}
/* Stronger light-mode overrides for Vega/Vega-Embed menus (covers nested lists, tooltips, and any generated menu nodes) */
.vega-embed details[open] > *,
.vega-embed .vega-actions-list,
.vega-embed .vega-actions-list *,
.vega-embed .vega-actions *,
.vega-embed .vega-actions button,
.vega-embed .vega-actions a,
.vega-embed .vega-actions a *,
.vega-embed .vega-actions summary,
.vega-embed .vega-actions summary * {
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #d4ccc0 !important;
}
/* Some browsers render the menu as a popover or use role="menu" children */
.vega-embed [role="menu"],
.vega-embed [role="menu"] * {
    background: #ffffff !important;
    color: #111111 !important;
}
[data-baseweb="tooltip"],
[data-baseweb="tooltip"] > div,
div[role="tooltip"] {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #d4ccc0 !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.12) !important;
}
[data-baseweb="tooltip"] *,
div[role="tooltip"] * {
    color: #111111 !important;
    -webkit-text-fill-color: #111111 !important;
}

.results-nav-mark { background: #0a0a0a !important; }

[data-testid="stMetric"] label { color: #525252 !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #000000 !important; }

[data-testid="stExpander"] summary { color: #0a0a0a !important; }

/* Ensure the small rounded Vega toolbar buttons match light card background */
.vega-embed .vega-actions,
.vega-embed .vega-actions > summary,
.vega-embed .vega-actions > summary *,
.vega-embed .vega-actions button,
.vega-embed .vega-actions div {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #d4ccc0 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
}
.vega-embed .vega-actions > summary {
    padding: 6px !important;
    border-radius: 12px !important;
}
.vega-embed .vega-actions svg,
.vega-embed .vega-actions a svg {
    fill: #111111 !important;
    stroke: #111111 !important;
}

/* Last-resort override: target any remaining wrappers or inline-styled nodes
   inside the Vega embed toolbar that may be rendered by different Vega versions
   or browser popovers. This block is intentionally very specific and placed at
   the end of the stylesheet to beat other rules. */
.main .vega-embed .vega-actions,
.main .vega-embed .vega-actions *,
.main .vega-embed details[open] > summary,
.main .vega-embed details[open] > summary *,
.main .vega-embed [role="toolbar"],
.main .vega-embed [role="toolbar"] *,
.main .vega-embed [role="menu"],
.main .vega-embed [role="menu"] *,
.main .vega-embed div[style*="background" i],
.main .vega-embed div[style*="background-color" i],
.main .vega-embed span[style*="background" i],
.main .vega-embed span[style*="background-color" i] {
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #d4ccc0 !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08) !important;
    border-radius: 12px !important;
}
.main .vega-embed .vega-actions::before,
.main .vega-embed .vega-actions::after,
.main .vega-embed details summary::before,
.main .vega-embed details summary::after {
    background: transparent !important;
}

/* Vega embed chrome only (not Streamlit chart toolbar icons) */
.vega-embed .vega-actions,
.vega-embed .vega-actions *,
.vega-embed details,
.vega-embed details summary {
    color: #111111 !important;
    -webkit-text-fill-color: #111111 !important;
}
.vega-embed svg,
.vega-embed img {
    filter: none !important;
}
.vega-embed [style*="filter" i] {
    filter: none !important;
}

/* If the browser is applying a forced-dark mode, this helps preserve intended light visuals for the embed */
html, body, .stApp, .main {
    color-scheme: light !important;
}




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

.main a, [data-testid="stMarkdownContainer"] a { color: #1d4ed8 !important; }

[data-testid="stExpander"] [data-testid="stVerticalBlock"] p,
[data-testid="stExpander"] [data-testid="stVerticalBlock"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #111111 !important;
}

hr { border-color: #e8e0d6 !important; }

/* Light theme: chart toolbar tray + fullscreen button */
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonContainer"] {
    background: #ffffff !important;
    color: #0a0a0a !important;
    border: 1px solid #d4ccc0 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
    padding: 0 !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"],
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"] button {
    background: transparent !important;
    color: #0a0a0a !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButtonContainer"]:hover {
    background: #f0ebe3 !important;
    border-color: #a8a29e !important;
}
[data-testid="stElementToolbar"]:has(+ [data-testid="stVegaLiteChart"]) [data-testid="stElementToolbarButton"] button:hover {
    background: transparent !important;
    border: none !important;
    color: #000000 !important;
}

/* Ensure hero / results header text and controls are high-contrast in light theme */
.main .hero, .stApp .hero, .block-container .hero,
.main .results-nav, .results-nav {
    background: #faf8f5 !important;
    border-color: #e8e0d6 !important;
    color: #0b0b0b !important;
}
.main .hero .hero-title, .hero .hero-title, .block-container .hero .hero-title,
.main .results-nav .results-nav-title, .results-nav .results-nav-title {
    color: #0b0b0b !important;
    -webkit-text-fill-color: #0b0b0b !important;
    opacity: 1 !important;
    text-shadow: none !important;
    filter: none !important;
    -webkit-text-stroke: 0 !important;
}
.main .hero .hero-sub, .hero .hero-sub, .hero .hero-meta,
.main .results-nav .results-nav-file, .results-nav .results-nav-file {
            color: #4b4b4b !important;
            opacity: 1 !important;
            text-shadow: none !important;
        }

/* Final forced fallbacks for any remaining inline-styled or injected nodes */
.main .hero *[style],
.main .hero [style*="color" i],
.main .hero [style*="-webkit-text-fill-color" i],
.main .results-nav *[style],
.main .results-nav [style*="color" i],
.main .results-nav [style*="-webkit-text-fill-color" i] {
    color: #0b0b0b !important;
    -webkit-text-fill-color: #0b0b0b !important;
    opacity: 1 !important;
    text-shadow: none !important;
}
</style>
"""
else:
    _theme_override_markup = "<style id='tb-app-theme-override'></style>"

st.markdown(_theme_override_markup, unsafe_allow_html=True)

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
                    _remember_uploaded_bill_payload(payload, usage_df, uf.name)
                    _fetch_uploaded_bill_options_api.clear()
                    for _key in (
                        "pastusage_recalc_account_option",
                        "latest_recalc_account_option",
                    ):
                        st.session_state.pop(_key, None)
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
# PAGE — PAST USAGE RESULTS
# ═══════════════════════════════════════════════════════════════
elif st.session_state["page"] == "op_past_results":
    render_past_usage_results_page()


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
    _results_tab_labels = ["Account", "Rate compare", "Schedule compare"]
    _results_tab = _select_persisted_tab(_results_tab_labels, "results_analysis_tab")
    if _results_tab == "Account":
        render_account_usage_charges_section(
            usage_df,
            profile=profile,
            widget_key_prefix="",
            show_profile_section=True,
        )
    elif _results_tab == "Rate compare":
        render_rate_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")
    elif _results_tab == "Schedule compare":
        render_schedule_compare_tab(usage_df, contract_id=contract_id, widget_key_prefix="")


else:
    st.session_state["page"] = "upload"
    st.rerun()

_inject_baseweb_menu_css()
