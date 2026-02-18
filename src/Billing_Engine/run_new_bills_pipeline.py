#!/usr/bin/env python3
"""
Run the new-bills OCR pipeline and billing engine in one step.

Order:
1) Parse PDFs -> write *_pivoted.xlsx to data/interim/new-bills-parsed
2) Run billing engine on pivoted files -> write outputs to export directory
"""

import sys
from pathlib import Path
import importlib.util
import pandas as pd
from typing import Iterable, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ENGINE_DIR = PROJECT_ROOT / "src" / "Billing_Engine"

def _load_module_from_path(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module

new_bills_v2 = _load_module_from_path("new_bills_v2", ENGINE_DIR / "new-bills_v2.py")
app_new = _load_module_from_path("app_new", ENGINE_DIR / "app_new.py")


def _upload_dataframe_to_db(df: pd.DataFrame, table_name: str, source_file: str) -> None:
    try:
        from src.Utils.database import engine
    except Exception as e:
        print(f"ERROR: Database engine not available: {e}", file=sys.stderr)
        return

    out = df.copy()
    out["source_file"] = source_file

    try:
        out.to_sql(table_name, con=engine, if_exists="append", index=False)
        print(f"  Saved to DB table: {table_name}")
    except Exception as e:
        print(f"  ERROR writing to DB table {table_name}: {e}", file=sys.stderr)


def _upload_extracted_and_pivoted(results: list) -> None:
    for res in results:
        if res.get("error"):
            print(f"  SKIP DB upload for {res.get('pdf')}: {res['error']}", file=sys.stderr)
            continue

        extracted_path = res.get("extracted")
        pivoted_path = res.get("pivoted")

        if extracted_path:
            try:
                df_extracted = pd.read_excel(extracted_path, dtype=str)
                _upload_dataframe_to_db(df_extracted, "usage_extracted", extracted_path.name)
            except Exception as e:
                print(f"  ERROR reading extracted file {extracted_path}: {e}", file=sys.stderr)

        if pivoted_path:
            try:
                df_pivoted = pd.read_excel(pivoted_path, dtype=str)
                _upload_dataframe_to_db(df_pivoted, "usage_pivoted", pivoted_path.name)
            except Exception as e:
                print(f"  ERROR reading pivoted file {pivoted_path}: {e}", file=sys.stderr)


def run_pipeline(write_to_db: bool = True, pdf_paths: Optional[Iterable[Path]] = None) -> list:
    print("\n=== Step 1: Parse new bills PDFs ===")
    if pdf_paths:
        results = [new_bills_v2.process_pdf(Path(p)) for p in pdf_paths]
    else:
        results = new_bills_v2.process_all_pdfs()

    if write_to_db and results:
        print("\n=== Step 1b: Upload extracted/pivoted data to DB ===")
        _upload_extracted_and_pivoted(results)

    print("\n=== Step 2: Run billing engine ===")
    app_new.main(write_to_db=write_to_db)

    print("\nPipeline complete.")
    return results


def main():
    run_pipeline(write_to_db=True)


if __name__ == "__main__":
    main()
