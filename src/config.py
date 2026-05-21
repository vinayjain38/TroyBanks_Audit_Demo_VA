import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_env(key, default=None):
    return os.getenv(key, default)


DB_TYPE = get_env("DB_TYPE", "sqlite")
DB_URL = None

if DB_TYPE == "postgres":
    DB_URL = URL.create(
        drivername="postgresql+psycopg2",
        username=get_env("DB_USER"),
        password=get_env("DB_PASSWORD"),
        host=get_env("DB_HOST"),
        port=get_env("DB_PORT"),
        database=get_env("DB_NAME"),
    )
else:
    _default_db = _REPO_ROOT / "data" / "project.db"
    DB_PATH = get_env("DB_PATH", str(_default_db))
    if not os.path.isabs(DB_PATH):
        DB_PATH = str((_REPO_ROOT / DB_PATH).resolve())
    DB_URL = f"sqlite:///{DB_PATH}"
