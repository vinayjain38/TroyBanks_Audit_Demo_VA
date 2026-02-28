"""
run_test.py - Runs the complete test flow: generate data -> process -> show results
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def show_results():
    """Display the output Excel file location"""
    output_file = Path("data") / "interim" / "anomaly_test_outputs" / "va_step2_anomalies.xlsx"
    
    if output_file.exists():
        print(f"\n{'='*60}")
        print("TEST COMPLETED SUCCESSFULLY")
        print(f"{'='*60}")
        print(f"\n✓ Output file created: {output_file}")
        print(f"  File size: {output_file.stat().st_size:,} bytes")
        print(f"\nYou can now open the Excel file to review the anomalies!")
        return True
    else:
        print(f"\n{'='*60}")
        print("TEST COMPLETED WITH ISSUES")
        print(f"{'='*60}")
        print(f"\n✗ Output file not found: {output_file}")
        return False


def main():
    """Run complete test flow"""
    
    # Get Python executable
    python_exe = sys.executable
    
    # Load environment
    if Path(".env").exists():
        from dotenv import load_dotenv
        load_dotenv()
    
    print("\n" + "="*60)
    print("TROY BANKS AUDIT DEMO - TEST SUITE")
    print("="*60)
    
    # Step 1: Generate test data
    success = run_command(
        [python_exe, "test_data_generator.py"],
        "STEP 1: Generating Test Data"
    )
    
    if not success:
        print("\n[ERROR] Failed to generate test data. Exiting.")
        return 1
    
    # Step 2: Run anomaly detection
    success = run_command(
        [python_exe, "src/va_step2_anomalies_db.py"],
        "STEP 2: Running Anomaly Detection"
    )
    
    if not success:
        print("\n[ERROR] Failed to run anomaly detection. Exiting.")
        return 1
    
    # Step 3: Show results
    show_results()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
