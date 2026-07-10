import pandas as pd
import os
from datetime import datetime

# --- CONFIG ---
DOWNLOAD_FOLDER = './downloads'
# Environment variable passed by AutomateAll.py
TARGET_MONTH = os.getenv("TARGET_MONTH") 

def get_target_month_name():
    target_month = os.getenv("TARGET_MONTH")
    received_date = os.getenv("RECEIVED_DATE")
    if target_month:
        return target_month.strip()
    if received_date:
        try:
            from datetime import datetime
            dt = datetime.strptime(received_date, '%d-%b-%Y')
            return dt.strftime('%B')
        except Exception:
            pass
    from datetime import datetime
    return datetime.now().strftime('%B')

def generate_athena_query():
    # 1. Find the latest file (excluding temp files)
    files = [
        os.path.join(DOWNLOAD_FOLDER, f) 
        for f in os.listdir(DOWNLOAD_FOLDER) 
        if f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')
    ]
    
    if not files:
        print("❌ No valid Excel files found to process.")
        return None
    
    target_month = get_target_month_name().lower()
    filtered_files = [f for f in files if target_month in os.path.basename(f).lower()]
    
    if filtered_files:
        latest_file = max(filtered_files, key=os.path.getmtime)
    else:
        latest_file = max(files, key=os.path.getmtime)
    print(f"🔍 Processing: {os.path.basename(latest_file)}")

    try:
        # 2. READ DATA DATE (Crucial for Catch-up Logic)
        # We read the 'Health' sheet to find the actual max date of the data
        date_df = pd.read_excel(latest_file, sheet_name='Health', engine='openpyxl')
        date_df['Date'] = pd.to_datetime(date_df['Date'])
        file_max_date = date_df['Date'].max()
        
        # This becomes our filename and filter reference
        data_date_str = file_max_date.strftime('%Y-%m-%d')
        
        # Calculate the 1st of the month for the data in the file
        # (If catching up for April 30, this will be April 1)
        first_date_of_data_month = file_max_date.replace(day=1).strftime('%Y-%m-%d')

        # 3. Extract IDs from 'Health Unique DPs'
        unique_df = pd.read_excel(latest_file, sheet_name='Health Unique DPs', engine='openpyxl')
        unique_ids = unique_df['DP ID'].dropna().astype(str).unique()
        sql_id_list = ",\n".join([f"'{id_val}'" for id_val in unique_ids])

        # 4. Filename logic: Always match the date INSIDE the file
        output_filename = f"query_{data_date_str}.sql"

        # 5. Build the final SQL string
        # We replace hardcoded 'current_month' logic with our dynamic first_date_of_data_month
        query = f"""
WITH partner_ids AS (
    SELECT dpno, _id
    FROM spectrum.partner 
    WHERE dpno IN (
{sql_id_list}
    )
),
input_clients AS (
    SELECT _id AS salesdetail_intermediaryloginid, dpno
    FROM partner_ids
),
filtered_pd AS (
    SELECT 
        pd.salesdetail_intermediaryloginid,
        pd._id,
        pd.createdat,
        pd.premiumdetails_netpremium,
        ic.dpno
    FROM spectrum.policydetail pd
    JOIN input_clients ic
        ON pd.salesdetail_intermediaryloginid = ic.salesdetail_intermediaryloginid
    WHERE pd.vertical = 'HEALTH'
      AND pd.businesstype IN ('NEW', 'PORTABILITY')
),
first_sale_classification AS (
    SELECT
        salesdetail_intermediaryloginid,
        MIN(createdat) AS first_sale_date
    FROM filtered_pd
    GROUP BY salesdetail_intermediaryloginid
),
client_status_flag AS (
    SELECT
        salesdetail_intermediaryloginid,
        first_sale_date,
        CASE
            WHEN first_sale_date < TIMESTAMP '2024-08-01' 
                THEN 'Already Active'
            WHEN first_sale_date < TIMESTAMP '{first_date_of_data_month}' 
                THEN 'Activated by LGLC'
            ELSE 'Inactive'
        END AS client_status
    FROM first_sale_classification
)
SELECT
    pd.dpno,
    pd.salesdetail_intermediaryloginid,
    COUNT(DISTINCT pd._id) AS policy_count,
    SUM(pd.premiumdetails_netpremium) AS total_netpremium,
    cs.client_status
FROM filtered_pd pd
JOIN client_status_flag cs
      ON pd.salesdetail_intermediaryloginid = cs.salesdetail_intermediaryloginid
WHERE pd.createdat >= TIMESTAMP '2024-01-01'
GROUP BY
    pd.dpno,
    pd.salesdetail_intermediaryloginid,
    cs.client_status
ORDER BY
    pd.dpno,
    pd.salesdetail_intermediaryloginid;
"""
        # 6. Save
        with open(output_filename, "w") as f:
            f.write(query)
            
        print("-" * 30)
        if TARGET_MONTH:
            print(f"🔄 MODE: CATCH-UP ({TARGET_MONTH})")
        else:
            print(f"🚀 MODE: REGULAR")
            
        print(f"📅 Data Date Identified: {data_date_str}")
        print(f"📅 Status Threshold:    {first_date_of_data_month}")
        print(f"💾 File Saved:          {output_filename}")
        print("-" * 30)
        
        return query, output_filename

    except Exception as e:
        print(f"❌ Error generating query: {e}")
        return None, None

if __name__ == "__main__":
    generate_athena_query()