import pandas as pd
import os

DOWNLOAD_FOLDER = './downloads'

def merge_athena_data():
    all_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if not f.startswith('~$')]
    excel_files = [f for f in all_files if f.endswith(('.xlsx', '.xls'))]
    csv_files = [f for f in all_files if f.endswith('.csv') and 'DP_Status' in f]

    if not excel_files or not csv_files:
        print("❌ Files missing in downloads folder.")
        return

    latest_excel = max(excel_files, key=os.path.getctime)
    latest_csv = max(csv_files, key=os.path.getctime)

    print(f"📂 Processing: {os.path.basename(latest_excel)}")

    try:
        # 1. Load CSV and Clean the Key
        df_status_raw = pd.read_csv(latest_csv)
        # Select 1st column (ID) and 5th column (Status)
        status_lookup = df_status_raw.iloc[:, [0, 4]].copy()
        status_lookup.columns = ['Key_ID', 'New_Status_Col'] 
        
        # Clean the CSV IDs
        status_lookup['Key_ID'] = status_lookup['Key_ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # 2. Load Excel Sheets
        sheets_to_update = ['Health', 'Health Unique DPs']
        xl = pd.ExcelFile(latest_excel)
        
        processed_dfs = {}

        for sheet in sheets_to_update:
            df = pd.read_excel(xl, sheet_name=sheet)

            # --- FIX 1: Remove any old 'DP Status' columns to prevent name clashes ---
            cols_to_remove = [c for c in df.columns if 'DP Status' in c or 'Key_ID' in c]
            if cols_to_remove:
                df = df.drop(columns=cols_to_remove)

            # Clean the Excel IDs
            df['DP ID'] = df['DP ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

            # 3. Perform Merge
            df = df.merge(status_lookup, left_on='DP ID', right_on='Key_ID', how='left')

            # --- FIX 2: Fill blanks and handle the .lower() bug correctly ---
            # Rename the merged column to the final desired name
            df = df.rename(columns={'New_Status_Col': 'DP Status'})
            
            # Fill NaN
            df['DP Status'] = df['DP Status'].fillna('Inactive')
            
            # Handle string-based 'nan' or empty strings
            df.loc[df['DP Status'].astype(str).str.lower() == 'nan', 'DP Status'] = 'Inactive'
            df.loc[df['DP Status'].astype(str) == '', 'DP Status'] = 'Inactive'

            # Drop the helper Key_ID column
            if 'Key_ID' in df.columns:
                df = df.drop(columns=['Key_ID'])
            
            processed_dfs[sheet] = df

        # 4. Save everything back
        with pd.ExcelWriter(latest_excel, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            processed_dfs['Health'].to_excel(writer, sheet_name='Health', index=False)
            processed_dfs['Health Unique DPs'].to_excel(writer, sheet_name='Health Unique DPs', index=False)
            df_status_raw.to_excel(writer, sheet_name='DP Status Data', index=False)

        print("-" * 30)
        print(f"✅ SUCCESS: {os.path.basename(latest_excel)} updated.")
        print("💡 No more blanks. No more naming errors.")
        print("-" * 30)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    merge_athena_data()