import pandas as pd

riders_df = pd.read_excel('data/interim/riders_new.xlsx')
print("RIDERS FILE:")
print(riders_df[['RATE SCHEDULE', 'AGGREGATE RIDER ADJUSTMENT PER KWH', 'AGGREGATE RIDER ADJUSTMENT PER KW']])

print("\n\nOUTPUT FILE - Profile4248:")
df = pd.read_excel('data/export/Profile4248_pivoted.xlsx')
print(f"\nDemand kW: min={df['demand_kw'].min()}, max={df['demand_kw'].max()}")
print(f"Non-zero demand count: {(df['demand_kw'] > 0).sum()}/{len(df)}")

print("\nSample rider charges (first 5 rows):")
print(df[['usage_kwh', 'demand_kw', 've100_rider_charge', 've110_rider_charge']].head())
