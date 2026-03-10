"""
Test script to upload a pivoted Excel file to the usage_bill table using the upload_usage_data function.
"""
from src.Utils.upload import upload_usage_data

if __name__ == "__main__":
    # Path to the Excel file to upload
    file_path = r"C:\Users\dimpl\Downloads\1172485896  EAP Report_pivoted.xlsx"
    upload_usage_data(file_path)
    print("Upload complete.")
