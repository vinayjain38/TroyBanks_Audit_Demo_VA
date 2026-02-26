from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from pendulum import datetime

PROJECT_ROOT = Path("/opt/project")
NEW_BILLS_DIR = PROJECT_ROOT / "data" / "raw" / "new-bills"
NEW_BILLS_PARSED_DIR = PROJECT_ROOT / "data" / "interim" / "new-bills-parsed"


@dag(
    dag_id="tariff_audit_pipeline",
    schedule=None,  # Manual trigger via API
    start_date=datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    tags=["tariff-audit", "billing"],
    params={
        "pdf_path": None,
    },
)
def tariff_audit_pipeline():
    @task(retries=0)
    def get_pdf_path(**context) -> str:
        """
        Retrieves PDF path from DAG run configuration.
        If not provided, picks the latest PDF from the new-bills directory.
        """
        # Try to get pdf_path from dag_run.conf (API trigger)
        dag_run = context.get("dag_run")
        if dag_run and dag_run.conf and "pdf_path" in dag_run.conf:
            pdf_path = dag_run.conf["pdf_path"]
            # Handle both absolute and relative paths
            if not pdf_path.startswith("/opt/project"):
                # Convert Windows path or relative path to container path
                pdf_name = Path(pdf_path).name
                pdf_path = str(NEW_BILLS_DIR / pdf_name)
        else:
            # Fallback: pick latest PDF if no path specified
            pdf_files = sorted(
                NEW_BILLS_DIR.glob("*.pdf"), 
                key=lambda p: p.stat().st_mtime, 
                reverse=True
            )
            if not pdf_files:
                raise AirflowFailException(f"No PDF files found in {NEW_BILLS_DIR}")
            pdf_path = str(pdf_files[0])
        
        # Validate file exists
        if not Path(pdf_path).exists():
            raise AirflowFailException(f"PDF file not found: {pdf_path}")
        
        return pdf_path

    @task(retries=0)
    def run_digital_ocr(pdf_path: str) -> None:
        cmd = [
            sys.executable,
            "/opt/project/src/Billing_Engine/new-bills_v3-digital-ocr.py",
            "--pdf",
            pdf_path,
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
        if result.returncode != 0:
            raise AirflowFailException(
                "new-bills_v3-digital-ocr failed\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    @task(retries=0)
    def run_profile_parser(pdf_path: str) -> None:
        cmd = [
            sys.executable,
            "/opt/project/src/Billing_Engine/new-bills-profile.py",
            "--pdf",
            pdf_path,
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
        if result.returncode != 0:
            raise AirflowFailException(
                "new-bills-profile failed\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    @task(trigger_rule="none_failed_min_one_success", retries=0)
    def run_billing_engine(pdf_path: str) -> None:
        pivoted_path = NEW_BILLS_PARSED_DIR / f"{Path(pdf_path).stem}_pivoted.xlsx"
        cmd = [
            sys.executable,
            "/opt/project/src/Billing_Engine/app_new2.py",
            "--pivoted",
            str(pivoted_path),
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
        if result.returncode != 0:
            raise AirflowFailException(
                "app_new2 failed\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    @task(retries=0)
    def run_upload_task(pdf_path: str) -> None:
        pivoted_path = NEW_BILLS_PARSED_DIR / f"{Path(pdf_path).stem}_pivoted.xlsx"
        cmd = [
            sys.executable,
            "/opt/project/src/Utils/upload.py",
            "--pivoted",
            str(pivoted_path),
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
        if result.returncode != 0:
            raise AirflowFailException(
                "upload.py failed\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    # Define task dependencies
    pdf_path = get_pdf_path()
    ocr_task = run_digital_ocr(pdf_path)
    profile_task = run_profile_parser(pdf_path)
    billing_task = run_billing_engine(pdf_path)
    upload_task = run_upload_task(pdf_path)
    
    # Set up the flow
    billing_task.set_upstream([ocr_task, profile_task])
    upload_task.set_upstream(billing_task)


_ = tariff_audit_pipeline()
