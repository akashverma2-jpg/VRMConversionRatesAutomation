import pandas as pd
import os
from datetime import datetime

DOWNLOAD_FOLDER = './downloads'

def generate_athena_query():
    # 1. Find the latest file, EXCLUDING temporary Excel lock files (starting with ~$)
    files = [
        os.path.join(DOWNLOAD_FOLDER, f) 
        for f in os.listdir(DOWNLOAD_FOLDER) 
        if f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')
    ]
    
    if not files:
        print("❌ No valid Excel files found to process.")
        return None
    
    latest_file = max(files, key=os.path.getctime)
    print(f"Reading data from: {os.path.basename(latest_file)}")

    try:
        # Using engine='openpyxl' to handle modern Mac Excel formats reliably
        df = pd.read_excel(latest_file, sheet_name='Health Unique DPs', engine='openpyxl')

        # 2. Extract DP IDs and format for SQL
        unique_ids = df['DP ID'].dropna().astype(str).unique()
        sql_id_list = ",\n".join([f"'{id_val}'" for id_val in unique_ids])

        # 3. Dynamic logic for the Query content (First day of current month)
        first_date_month = datetime.today().replace(day=1).strftime('%Y-%m-%d')
        
        # 4. Dynamic filename: query_YYYY-MM-DD.sql
        current_date_str = datetime.today().strftime('%Y-%m-%d')
        output_filename = f"query_{current_date_str}.sql"

        # 5. Build the final SQL string
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
            WHEN first_sale_date < TIMESTAMP '{first_date_month}' 
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
        # 6. Save with the new timestamped filename
        with open(output_filename, "w") as f:
            f.write(query)
            
        print("-" * 30)
        print(f"✅ Success!")
        print(f"📅 Query Date: {first_date_month}")
        print(f"💾 File Saved: {output_filename}")
        print("-" * 30)
        
        return query, output_filename

    except Exception as e:
        print(f"❌ Error generating query: {e}")
        return None, None

if __name__ == "__main__":
    generate_athena_query()