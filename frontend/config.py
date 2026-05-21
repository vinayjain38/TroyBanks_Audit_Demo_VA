"""App configuration: paths, environment, backend URL."""

from pathlib import Path
import os
import sys

FRONTEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = FRONTEND_DIR.parent
ROOT = FRONTEND_DIR
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- Optional .env (local dev): repo root first, then frontend/ ----
for _env_file in (REPO_ROOT / ".env", FRONTEND_DIR / ".env"):
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

os.environ.setdefault("TESSDATA_PREFIX", "/opt/anaconda3/share/tessdata")
os.environ.setdefault("TESSERACT_PATH", "/opt/anaconda3/bin/tesseract")

# Host-run Streamlit: use same host port as API_HOST_PORT in docker-compose (default 8000).
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")
