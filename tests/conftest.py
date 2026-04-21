import os

# Allow importing src.* without a live DB during unit tests — config.py defaults to SQLite.
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("DB_PATH", "data/test.db")
