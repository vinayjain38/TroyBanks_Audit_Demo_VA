import pandas as pd

riders = pd.read_excel('data/interim/riders_new.xlsx')
print("Rider rates per kW:")
print(riders[['RATE SCHEDULE', 'AGGREGATE RIDER ADJUSTMENT PER KW']])
