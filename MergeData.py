import pandas as pd
import os
import re

# --- CONFIG ---
DOWNLOAD_FOLDER = './downloads'

def get_target_files():
    """
    Identifies the Excel file and the corresponding date-stamped CSV.
    Ensures that data for April 30th merges with the April 30th status CSV.
    """
    all_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if not f.startswith('~$')]
    excel_files = [f for f in all_files if f.endswith(('.xlsx', '.xls'))]
    
    if not excel_files:
        print("❌ No Excel files found in downloads folder.")
        return None, None, None

    # 1. Identify the most recently downloaded Excel file
    latest_excel = max(excel_files, key=os.path.getctime)
    
    # 2. Extract the actual data date from the 'Health' sheet
    try:
        df_date = pd.read_excel(latest_excel, sheet_name='Health', engine='openpyxl')
        data_date = pd.to_datetime(df_date['Date']).max().strftime('%Y-%m-%d')
    except Exception as e:
        print(f"⚠️ Could not extract date from Excel: {e}")
        return latest_excel, None, None

    # 3. Specifically look for the CSV matching this data date
    target_csv_name = f"DP_Status_{data_date}.csv"
    target_csv_path = os.path.join(DOWNLOAD_FOLDER, target_csv_name)

    if not os.path.exists(target_csv_path):
        # Fallback to latest ctime CSV if the specific date-stamped one isn't found
        print(f"⚠️ Specific file {target_csv_name} not found. Checking latest CSV...")
        csv_files = [f for f in all_files if f.endswith('.csv') and 'DP_Status' in f]
        if not csv_files:
            return latest_excel, None, data_date
        target_csv_path = max(csv_files, key=os.path.getctime)

    return latest_excel, target_csv_path, data_date

def merge_athena_data():
    latest_excel, latest_csv, data_date = get_target_files()

    if not latest_excel or not latest_csv:
        print(f"❌ Required files missing for date: {data_date}")
        return

    print(f"📂 Processing Excel: {os.path.basename(latest_excel)}")
    print(f"🔗 Merging Status CSV: {os.path.basename(latest_csv)} (Target Date: {data_date})")

    try:
        # 1. Load CSV and Clean the Key
        df_status_raw = pd.read_csv(latest_csv)
        # Select 1st column (ID) and 5th column (Status)
        status_lookup = df_status_raw.iloc[:, [0, 4]].copy()
        status_lookup.columns = ['Key_ID', 'New_Status_Col'] 
        
        # Clean the CSV IDs (handle floats and strings)
        status_lookup['Key_ID'] = status_lookup['Key_ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # 2. Load Excel
        sheets_to_update = ['Health', 'Health Unique DPs']
        xl = pd.ExcelFile(latest_excel)
        processed_dfs = {}

        for sheet in sheets_to_update:
            df = pd.read_excel(xl, sheet_name=sheet)

            # --- CLEANING: Remove old DP Status columns to prevent duplicates ---
            cols_to_remove = [c for c in df.columns if 'DP Status' in c or 'Key_ID' in c]
            if cols_to_remove:
                df = df.drop(columns=cols_to_remove)

            # Clean the Excel IDs
            df['DP ID'] = df['DP ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

            # 3. Perform Merge
            df = df.merge(status_lookup, left_on='DP ID', right_on='Key_ID', how='left')

            # --- REFINEMENT: Fill blanks and handle formatting ---
            df = df.rename(columns={'New_Status_Col': 'DP Status'})
            df['DP Status'] = df['DP Status'].fillna('Inactive')
            
            # Catch string-based 'nan' or empty values
            df.loc[df['DP Status'].astype(str).str.lower() == 'nan', 'DP Status'] = 'Inactive'
            df.loc[df['DP Status'].astype(str) == '', 'DP Status'] = 'Inactive'

            # Drop helper column
            if 'Key_ID' in df.columns:
                df = df.drop(columns=['Key_ID'])
            
            processed_dfs[sheet] = df

        # 4. Save everything back including the raw status data for audit
        with pd.ExcelWriter(latest_excel, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            processed_dfs['Health'].to_excel(writer, sheet_name='Health', index=False)
            processed_dfs['Health Unique DPs'].to_excel(writer, sheet_name='Health Unique DPs', index=False)
            # Add a sheet for manual verification if needed
            df_status_raw.to_excel(writer, sheet_name='DP Status Data', index=False)

        print("-" * 30)
        print(f"✅ SUCCESS: {os.path.basename(latest_excel)} updated for {data_date}.")
        print("-" * 30)

    except Exception as e:
        print(f"❌ Error during merge: {e}")

if __name__ == "__main__":
    merge_athena_data()