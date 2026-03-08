# run_test.py
import sys
from pathlib import Path

# Adjust this path if your Excel file is stored somewhere else
TARIFF_FILE = "data/raw/Mini_Edit_VEPGA_Schedules_Compact.xlsx"

# Import our new, smart versioning function from your upload.py script
# (Assuming upload.py is inside src/Utils or just in src. Adjust the import if needed)
from src.Utils.upload import upload_tariffs_versioned 

print("Starting initial Tariff population...")

# Pass the file to the doorway!
upload_tariffs_versioned(TARIFF_FILE)

print("Done! Check DBeaver!")