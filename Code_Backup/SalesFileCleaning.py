import pandas as pd
import os
from openpyxl import load_workbook

DOWNLOAD_FOLDER = './downloads'

def clean_excel_sheets():
    # 1. Find the latest file
    files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) 
             if f.endswith(('.xlsx', '.xls'))]
    if not files:
        print("No Excel files found.")
        return
    
    latest_file = max(files, key=os.path.getctime)
    print(f"Opening file: {latest_file}")

    try:
        # 2. Read the 'Health' sheet
        # We read the whole sheet to ensure we don't lose other columns
        df = pd.read_excel(latest_file, sheet_name='Health')

        # 3. Clean the 'DP ID' column in the original data (Text to Columns logic)
        # This replaces 'DP-4033623' with '4033623' in the original 'Health' sheet
        df['DP ID'] = df['DP ID'].astype(str).str.split('-').str[-1].str.strip()

        # 4. Create the Unique version
        df_unique = df.drop_duplicates(subset=['DP ID'], keep='first')

        # 5. Write back to the Excel file
        # 'replace' will overwrite the existing 'Health' sheet with the cleaned version
        with pd.ExcelWriter(latest_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            # Update original sheet
            df.to_excel(writer, sheet_name='Health', index=False)
            # Create/Update unique sheet
            df_unique.to_excel(writer, sheet_name='Health Unique DPs', index=False)

        print("-" * 30)
        print(f"✅ 'Health' sheet cleaned (DP IDs updated).")
        print(f"✅ 'Health Unique DPs' sheet created/renamed.")
        print(f"📊 Total Unique DPs found: {len(df_unique)}")
        print("-" * 30)
        
        # Format the IDs for your Athena Query (needed for Part 3)
        id_list = ", ".join([f"'{str(id_val)}'" for id_val in df_unique['DP ID'].unique() if id_val != 'nan'])
        return id_list

    except Exception as e:
        print(f"❌ Error during Excel processing: {e}")
        return None

if __name__ == "__main__":
    sql_ready_ids = clean_excel_sheets()