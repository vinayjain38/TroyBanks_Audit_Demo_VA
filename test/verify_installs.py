"""
Verify that all dependencies are installed and ready for table extraction
"""

import sys

missing = []
required = {
    'cv2': 'opencv-python-headless',
    'fitz': 'PyMuPDF',
    'pytesseract': 'pytesseract',
    'PIL': 'Pillow',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'openpyxl': 'openpyxl',
    'dotenv': 'python-dotenv',
}

print("="*70)
print("VERIFYING SETUP FOR SCANNED PDF TABLE EXTRACTION")
print("="*70)
print()

for module, package in required.items():
    try:
        if module == 'cv2':
            import cv2
            print(f"[OK] {package} (cv2)")
        elif module == 'fitz':
            import fitz
            print(f"[OK] {package} (fitz)")
        elif module == 'PIL':
            from PIL import Image
            print(f"[OK] {package} (PIL)")
        elif module == 'dotenv':
            from dotenv import load_dotenv
            print(f"[OK] {package} (dotenv)")
        else:
            __import__(module)
            print(f"[OK] {package} ({module})")
    except ImportError:
        print(f"[MISSING] {package} ({module})")
        missing.append(package)

print()
print("="*70)

if missing:
    print("MISSING DEPENDENCIES:")
    print("="*70)
    print(f"\nPlease install: pip install {' '.join(missing)}\n")
    sys.exit(1)
else:
    print("ALL DEPENDENCIES INSTALLED ✓")
    print("="*70)
    
    # Check Tesseract
    print("\nChecking Tesseract OCR...")
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        print(f"[OK] Tesseract version: {version}")
    except Exception as e:
        print(f"[MISSING] Tesseract not found: {e}")
        print("\nPlease install Tesseract OCR:")
        print("  https://github.com/UB-Mannheim/tesseract/wiki")
        print("\nOr set TESSERACT_PATH in .env file")
    
    print("\n" + "="*70)
    print("SETUP VERIFICATION COMPLETE")
    print("="*70)
    print()
