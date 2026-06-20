import pandas as pd

df = pd.read_excel('Performance_Breakdown_2026-06-19.xlsx', sheet_name='Email Level')
vijay = df[df['Email'].str.contains('g.vijay', na=False, case=False)]
for _, row in vijay.iterrows():
    print(repr(row['Email']), row['Team'])
