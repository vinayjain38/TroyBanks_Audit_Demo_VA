PROJECT_STATUS_AND_TODO
========================

Launch guide (Docker: default API 8000, UI 8501 → optional Airflow → EC2 later):
  STEPS.txt

Quick local reference:
  LOCAL_RUN.txt

Open in Microsoft Word (or compatible):
  PROJECT_STATUS_AND_ARCHITECTURE.docx

That document includes:
  • What was completed (backend/frontend/Docker/refactors)
  • What you still need to do (env, DB init, EC2, optional hardening)
  • Short architecture summary
  • File-by-file explanations

To regenerate the Word file after edits:
  python docs/PROJECT_STATUS_AND_TODO/generate_documentation_docx.py
  (Requires: pip install python-docx)
