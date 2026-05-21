from sqlalchemy import text
from backend.db_usage import engine
import pandas as pd

with engine.connect() as conn:
    raw = pd.read_sql(text('SELECT * FROM usage_bill WHERE "accountNumber" IS NOT NULL'), conn)

print('raw shape', raw.shape)
print('unique account numbers', raw['accountNumber'].astype(str).unique())
print('count 009028500412', (raw['accountNumber'].astype(str) == '009028500412').sum())
print('count TEST', (raw['accountNumber'].astype(str) == 'TEST').sum())
print(raw.loc[raw['accountNumber'].astype(str) == '009028500412', ['batch_id', 'source_pdf', 'accountName', 'year', 'uploaded_at']].head(5).to_string(index=False))

if 'accountName' in raw.columns:
    customer = raw['accountName'].fillna("")
else:
    customer = pd.Series(["Unknown Customer"] * len(raw))

bill_year = raw['year'].astype(str) if 'year' in raw.columns else pd.Series(["Unknown"] * len(raw))

batch_col = raw['batch_id'].fillna("").astype(str).str.strip() if 'batch_id' in raw.columns else pd.Series([""] * len(raw), index=raw.index)
src_pdf = raw['source_pdf'].fillna("").astype(str) if 'source_pdf' in raw.columns else pd.Series([""] * len(raw), index=raw.index)

grouped = pd.DataFrame({
    'batch_id': batch_col,
    'source_pdf': src_pdf,
    'account_number': raw['accountNumber'].astype(str).str.strip(),
    'customer_name': customer.astype(str).replace('', 'Unknown Customer'),
    'bill_year': bill_year,
    'uploaded_at': pd.to_datetime(raw['uploaded_at'], errors='coerce') if 'uploaded_at' in raw.columns else pd.NaT,
})
print('grouped shape', grouped.shape)
print('grouped unique accounts', grouped['account_number'].unique())
print('grouped count 009028500412', (grouped['account_number'] == '009028500412').sum())
print('grouped count TEST', (grouped['account_number'] == 'TEST').sum())
print(grouped.loc[grouped['account_number'] == '009028500412'].head(10).to_string(index=False))

grouped['row_count'] = 1
res = grouped.groupby(['batch_id', 'source_pdf', 'account_number', 'customer_name', 'bill_year', 'uploaded_at'], as_index=False, dropna=False)['row_count'].sum()
print('res shape', res.shape)
print('res unique accounts', res['account_number'].unique())
print(res.sort_values(['uploaded_at', 'account_number', 'bill_year'], ascending=[False, True, True]).to_string(index=False))
