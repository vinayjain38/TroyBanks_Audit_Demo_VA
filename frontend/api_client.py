"""HTTP client for the Troy & Banks FastAPI backend."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config import BACKEND_URL

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
            key = [c for c in ("bill_period_end",) if c in combined.columns]
            return combined[key + take]

        return _run


SCHEDULE_FUNCS = _ScheduleFuncProxy()


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
