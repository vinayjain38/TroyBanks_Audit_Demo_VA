from src.Utils.database import engine
from sqlalchemy import text
import pandas as pd
with engine.connect() as conn:
    raw = pd.read_sql(text('SELECT * FROM usage_bill WHERE "accountNumber" IS NOT NULL ORDER BY id'), conn)
print('raw shape', raw.shape)
print('columns', raw.columns.tolist())
print('accountNumber unique', raw['accountNumber'].unique())
print('accountName unique count', raw['accountName'].nunique(dropna=False))
print('year unique', raw['year'].unique())
customer = raw['accountName'].fillna("")
print('customer sample', customer.head(5).tolist())
account_number = raw['accountNumber'].astype(str).str.strip()
print('account_number sample', account_number.head(10).tolist())
print('account_number unique', account_number.unique())
print('batch_id sample', raw['batch_id'].head(10).tolist())
print('uploaded_at types', raw['uploaded_at'].dtype)
bill_year = raw['year'].astype(str)
print('bill_year sample', bill_year.head(10).tolist())
body = {
    'batch_id': raw['batch_id'].fillna('').astype(str).str.strip(),
    'source_pdf': raw['source_pdf'].fillna('').astype(str),
    'account_number': account_number,
    'customer_name': customer.astype(str).replace('', 'Unknown Customer'),
    'bill_year': bill_year,
    'uploaded_at': pd.to_datetime(raw['uploaded_at'], errors='coerce'),
}
grouped = pd.DataFrame(body)
print('grouped columns', grouped.columns.tolist())
print(grouped.head(10))
print('grouped count before', len(grouped))
out = grouped.groupby(['batch_id','source_pdf','account_number','customer_name','bill_year','uploaded_at'], as_index=False)['account_number'].count()
print(out)
print(out['account_number'].unique())
print('shape', out.shape)
