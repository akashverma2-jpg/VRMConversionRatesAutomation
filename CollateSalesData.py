import pandas as pd
import os
from CalculateMetrics import TEAM_MAP, clean_string, map_bdm_to_email

# --- CONFIG ---
DOWNLOAD_FOLDER = './downloads'
MASTER_FILE = 'Collated_Sales_Master.xlsx'

def collate_sales_data():
    all_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if not f.startswith('~$')]
    excel_files = [f for f in all_files if f.endswith(('.xlsx', '.xls'))]
    
    if not excel_files:
        print("❌ No Excel files found to collate.")
        return

    latest_excel = max(excel_files, key=os.path.getctime)
    print(f"\n📂 Collating Data from: {os.path.basename(latest_excel)}")

    try:
        # 1. Read the parsed Health sheet
        df_daily = pd.read_excel(latest_excel, sheet_name='Health', engine='openpyxl')
        
        # Determine the correct column names flexibly in case of slight spacing differences
        cols = df_daily.columns.str.strip()
        df_daily.columns = cols
        
        # Required columns mapping
        required_cols = {
            'Date': 'Date',
            'BDM Name': 'BDM Name', 
            'DP ID': 'DP ID',
            'Net Premium': 'Net Premium',
            'DP Status': 'DP Status'
        }
        
        # Ensure required columns exist
        missing_cols = [k for k in required_cols.keys() if k not in df_daily.columns]
        if missing_cols:
            print(f"⚠️ Missing columns in daily file: {missing_cols}. Collation skipped.")
            return
            
        # Extract and order the specific columns
        df_daily_subset = df_daily[['Date', 'BDM Name', 'DP ID', 'Net Premium', 'DP Status']].copy()
        
        # Standardize formats to avoid mismatch during deduplication
        df_daily_subset['Date'] = pd.to_datetime(df_daily_subset['Date']).dt.strftime('%Y-%m-%d')
        df_daily_subset['DP ID'] = df_daily_subset['DP ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        # Add Team column
        df_daily_subset['BDM Name Cleaned'] = df_daily_subset['BDM Name'].apply(clean_string)
        bdm_to_email_map = map_bdm_to_email(df_daily_subset['BDM Name Cleaned'].dropna().unique(), list(TEAM_MAP.keys()))
        df_daily_subset['Email'] = df_daily_subset['BDM Name Cleaned'].map(bdm_to_email_map)
        df_daily_subset['Team'] = df_daily_subset['Email'].map(TEAM_MAP).fillna('unknown')
        df_daily_subset = df_daily_subset.drop(columns=['BDM Name Cleaned', 'Email'])

        
        # 2. Load the Master File (or create a blank one if it doesn't exist)
        if os.path.exists(MASTER_FILE):
            df_master = pd.read_excel(MASTER_FILE, engine='openpyxl')
            # Drop the Serial No. before merging, we will recalculate it
            if 'Serial No.' in df_master.columns:
                df_master = df_master.drop(columns=['Serial No.'])
        else:
            df_master = pd.DataFrame()
            
        # 3. Concatenate
        df_combined = pd.concat([df_master, df_daily_subset], ignore_index=True)
        
        # 4. Deduplicate (The DP ID, Date, Net Premium logic)
        # Keep the 'last' entry so that updated DP statuses override older ones
        initial_count = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset=['DP ID', 'Date', 'Net Premium'], keep='last')
        final_count = len(df_combined)
        
        # 5. Add Serial Number
        df_combined.insert(0, 'Serial No.', range(1, len(df_combined) + 1))
        
        # 6. Save back to Master File
        df_combined.to_excel(MASTER_FILE, index=False)
        
        print(f"✅ Master File Updated successfully!")
        print(f"📊 Rows processed: {len(df_daily_subset)} | Duplicates handled: {initial_count - final_count} | Master File Total Rows: {final_count}")

    except Exception as e:
        print(f"❌ Error during collation: {e}")

if __name__ == "__main__":
    collate_sales_data()
