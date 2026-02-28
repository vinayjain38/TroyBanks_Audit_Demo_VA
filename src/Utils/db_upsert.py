# src/Utils/db_upsert.py
import pandas as pd
from sqlalchemy import text
import uuid

def upsert_dataframe(df, table_name, engine, unique_cols):
    """
    Safely upserts a Pandas DataFrame into a PostgreSQL table using a staging table.
    Overwrites existing rows if the unique_cols match, otherwise inserts new rows.
    """
    if df.empty:
        print("[INFO] DataFrame is empty. Nothing to upsert.")
        return

    # 1. Create a unique temporary staging table name
    temp_table = f"temp_staging_{uuid.uuid4().hex[:8]}"
    
    # 2. Upload the raw dataframe to the staging table
    df.to_sql(temp_table, con=engine, if_exists='replace', index=False)
    
    # 3. Build the dynamic UPSERT query
    update_cols = [col for col in df.columns if col not in unique_cols]
    
    # Format column names safely with double quotes for Postgres
    set_clause_items = [f'"{col}" = EXCLUDED."{col}"' for col in update_cols]
    
    # Force the uploaded_at timestamp to update on every conflict overwrite
    if "uploaded_at" not in update_cols:
        set_clause_items.append('"uploaded_at" = CURRENT_TIMESTAMP')
        
    set_clause = ", ".join(set_clause_items)
    insert_cols = ", ".join([f'"{col}"' for col in df.columns])
    conflict_cols = ", ".join([f'"{col}"' for col in unique_cols])
    
    upsert_query = f"""
        INSERT INTO {table_name} ({insert_cols})
        SELECT {insert_cols} FROM {temp_table}
        ON CONFLICT ({conflict_cols})
        DO UPDATE SET {set_clause};
    """
    
    # 4. Execute the query and drop the staging table
    try:
        with engine.begin() as conn:
            conn.execute(text(upsert_query))
            conn.execute(text(f"DROP TABLE {temp_table};"))
        print(f"[SUCCESS] Upserted {len(df)} rows into '{table_name}'.")
    except Exception as e:
        print(f"[ERROR] Upsert failed: {e}")
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table};"))
        raise e