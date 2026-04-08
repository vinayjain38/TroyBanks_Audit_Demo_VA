import os

# Allow importing src.* without a live Postgres URL during unit tests.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
