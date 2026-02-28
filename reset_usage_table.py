from src.Utils.database import engine, Base
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS usage_bill"))
    conn.commit()
    print("Dropped usage_bill table")

Base.metadata.create_all(bind=engine)
print("Recreated all tables")
