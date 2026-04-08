FROM apache/airflow:3.1.7

USER root

RUN apt-get update \
    ; apt-get install -y --no-install-recommends \
        tesseract-ocr \
        ghostscript \
        poppler-utils \
    ; apt-get clean \
    ; rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --no-cache-dir \
        pymupdf \
        pytesseract \
        pillow \
        camelot-py \
        opencv-python-headless \
        pandas \
        openpyxl \
        python-dotenv
