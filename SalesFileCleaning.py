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
        # 1a. Identify the correct 'Health' sheet
        xl = pd.ExcelFile(latest_file)
        matching_sheets = []
        for sheet in xl.sheet_names:
            clean_name = sheet.strip().lower()
            if 'health' in clean_name and 'unique' not in clean_name:
                matching_sheets.append(sheet)
                
        if not matching_sheets:
            print("❌ 'Health' sheet not found in the file.")
            return None
        elif len(matching_sheets) == 1:
            target_sheet = matching_sheets[0]
        else:
            print("⚠️ Multiple sheets found with 'health' in the name:")
            for idx, name in enumerate(matching_sheets):
                print(f"  {idx + 1}. {name}")
            
            while True:
                try:
                    choice = int(input(f"Please enter the number of the correct sheet (1-{len(matching_sheets)}): "))
                    if 1 <= choice <= len(matching_sheets):
                        target_sheet = matching_sheets[choice - 1]
                        break
                    else:
                        print("❌ Invalid choice. Please select a number from the list.")
                except ValueError:
                    print("❌ Please enter a valid number.")

        # 2. Read the identified 'Health' sheet
        # We read the whole sheet to ensure we don't lose other columns
        df = pd.read_excel(latest_file, sheet_name=target_sheet)

        # 3. Clean the 'DP ID' column in the original data (Text to Columns logic)
        # This replaces 'DP-4033623' with '4033623' in the original sheet
        df['DP ID'] = df['DP ID'].astype(str).str.split('-').str[-1].str.strip()

        # 4. Create the Unique version
        df_unique = df.drop_duplicates(subset=['DP ID'], keep='first')

        # 5. Write back to the Excel file
        # 'replace' will overwrite the existing sheet with the cleaned version
        with pd.ExcelWriter(latest_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            # If the original name wasn't exactly 'Health', remove the original one
            if target_sheet != 'Health' and target_sheet in writer.book.sheetnames:
                del writer.book[target_sheet]
            
            # Update original sheet and rename it exactly to 'Health' for downstream scripts
            df.to_excel(writer, sheet_name='Health', index=False)
            # Create/Update unique sheet
            df_unique.to_excel(writer, sheet_name='Health Unique DPs', index=False)

        print("-" * 30)
        print(f"✅ '{target_sheet}' sheet cleaned and saved as 'Health' (DP IDs updated).")
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