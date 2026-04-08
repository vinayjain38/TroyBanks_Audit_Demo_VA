"""Load Billing_Engine modules whose filenames contain hyphens (not valid Python import names)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_from_path(module_name: str, relative_path: str):
    path = _PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {relative_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_bills_v2 = _load_from_path("new_bills_v2", "src/Billing_Engine/new-bills_v2.py")
_bills_profile = _load_from_path("new_bills_profile", "src/Billing_Engine/new-bills-profile.py")

extract_all_usage_tables = _bills_v2.extract_all_usage_tables
pivot_usage_table = _bills_v2.pivot_usage_table
ocr_pdf_page = _bills_profile.ocr_pdf_page
parse_dominion_account_profile = _bills_profile.parse_dominion_account_profile
