"""Table styling, export helpers, and dataframe utilities."""

import inspect
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import altair as alt
except ImportError:
    alt = None

from api_client import (
    BACKEND_URL,
    SCHEDULE_FUNCS,
    _api_request,
    _calc_sources,
    _export_bytes_via_api,
    _fetch_uploaded_bill_options_api,
    _pastusage_batches_api_payload,
    _records_clean,
    _remember_uploaded_bill_payload,
    _schedule_options,
    _session_uploaded_bill_options,
    _session_usage_records_for_batches,
    _usage_records_for_api,
    add_recalc_history,
    fetch_saved_bill_profile,
    fetch_uploaded_bill_options,
    fetch_version_options,
)
from theme import select_persisted_tab, theme_palette


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


_DATE_ONLY_COLUMNS = frozenset({"bill_period_end", "bill period", "bill period end"})


def _bill_period_display_mask(series: pd.Series) -> pd.Series:
    return series.astype(str).str.upper() == "TOTAL"


def normalize_bill_period_key(series: pd.Series) -> pd.Series:
    """Canonical billing period for merges (calendar date, no time-of-day drift)."""
    raw = series.copy()
    tot_mask = _bill_period_display_mask(raw)
    parsed = pd.to_datetime(raw, errors="coerce")
    # normalize() strips time so 2024-03-21 00:00:00 and 2024-03-21 always match
    keys = parsed.dt.normalize()
    out = keys.dt.strftime("%Y-%m-%d")
    out = out.where(parsed.notna(), raw.astype(str))
    out.loc[tot_mask] = "TOTAL"
    return out


def format_date_only_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Show billing period as YYYY-MM-DD (no 00:00:00) for display tables."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        name = str(col).lower()
        is_period_col = (
            name in _DATE_ONLY_COLUMNS
            or col == "Bill Period"
            or (pd.api.types.is_datetime64_any_dtype(out[col]) and "period" in name)
        )
        if not is_period_col:
            continue
        out[col] = normalize_bill_period_key(out[col])
    return out


def standardize_usage_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize any uploaded bill usage frame before session storage or API calls."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "bill_period_end" in out.columns:
        out["bill_period_end"] = pd.to_datetime(out["bill_period_end"], errors="coerce")
        out = out.dropna(subset=["bill_period_end"])
        out = out.sort_values("bill_period_end").reset_index(drop=True)
    for col in ("usage_kwh", "charges", "demand_kw"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "contract_account" in out.columns:
        out["contract_account"] = out["contract_account"].astype(str).str.strip()
    return out


def _st_dataframe(df: pd.DataFrame, **kwargs) -> None:
    """``st.dataframe`` wrapper: older Streamlit builds omit ``key`` on dataframes."""
    if not _DATAFRAME_SUPPORTS_KEY:
        kwargs.pop("key", None)
    if isinstance(df, pd.DataFrame):
        df = format_date_only_columns(df)
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
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
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




def add_total(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = df.select_dtypes(include=["number"]).columns
    totals = df[numeric_cols].sum()
    row = {col: None for col in df.columns}
    for col in numeric_cols:
        row[col] = totals[col]
    row["bill_period_end"] = "TOTAL"
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def merge_schedule_output(base: pd.DataFrame, schedule_out: pd.DataFrame) -> pd.DataFrame:
    """Align schedule API columns to usage rows by bill_period_end (not row index).

    The calculate API may sort/filter rows (e.g. drop zero-usage months); positional assignment
    mis-labels periods. Merge on a normalized date key so any future upload stays aligned.
    """
    if schedule_out is None or schedule_out.empty:
        return base.copy()
    left = base.reset_index(drop=True).copy()
    right = schedule_out.reset_index(drop=True).copy()
    if "bill_period_end" not in left.columns or "bill_period_end" not in right.columns:
        return pd.concat([left, right], axis=1)

    left["_period_key"] = normalize_bill_period_key(left["bill_period_end"])
    right["_period_key"] = normalize_bill_period_key(right["bill_period_end"])
    tot_left = left["_period_key"] == "TOTAL"
    tot_right = right["_period_key"] == "TOTAL"
    left = left.loc[~tot_left].copy()
    right = right.loc[~tot_right].copy()
    if right["_period_key"].duplicated().any():
        right = right.drop_duplicates(subset=["_period_key"], keep="last")

    value_cols = [
        c for c in right.columns
        if c not in ("bill_period_end", "_period_key")
    ]
    right_merge = right[["_period_key", *value_cols]].copy()
    overlap = [c for c in value_cols if c in left.columns]
    right_merge = right_merge.drop(columns=overlap, errors="ignore")
    merged = left.merge(right_merge, on="_period_key", how="left")
    merged = merged.drop(columns=["_period_key"], errors="ignore")
    return merged.reset_index(drop=True)


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


