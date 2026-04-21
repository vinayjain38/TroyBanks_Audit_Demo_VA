import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()


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
    DB_PATH = get_env("DB_PATH", "data/project.db")
    DB_URL = f"sqlite:///{DB_PATH}"
