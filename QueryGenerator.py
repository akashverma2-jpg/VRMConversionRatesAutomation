import pandas as pd
import os
from datetime import datetime

from PipelineUtils import get_target_sales_file, get_target_month_name

# --- CONFIG ---
DOWNLOAD_FOLDER = './downloads'
# Environment variable passed by AutomateAll.py
TARGET_MONTH = os.getenv("TARGET_MONTH") 

def generate_athena_query():
    # 1. Find the latest file robustly (month abbreviation + internal max date)
    latest_file = get_target_sales_file(DOWNLOAD_FOLDER)
    if not latest_file:
        print("❌ No valid Excel files found to process.")
        return None
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
        # 6. Save DP Status Query
        with open(output_filename, "w") as f:
            f.write(query)

        # 7. Generate & Save Favourite Supply Query
        fav_query = f"""SELECT dp_id AS dp_id,
       agent_mapped AS agent_mapped,
       dp_name AS dp_name,
       dp_mobile_number AS dp_mobile_number,
       dp_rm_name AS dp_rm_name,
       snapshot_date AS snapshot_date
FROM
  (WITH config AS
     (SELECT 0 AS month_offset),
        date_bounds AS
     (SELECT date_add('month', -cfg.month_offset, date_trunc('month', CAST('{data_date_str}' AS DATE))) AS target_month_start,
             date_format(date_add('day', -1, date_add('month', -cfg.month_offset, date_trunc('month', CAST('{data_date_str}' AS DATE)))), '%Y-%m-%d') AS fav_base_sqldate
      FROM config cfg) SELECT dp_id,
                              agent_mapped,
                              dp_name,
                              dp_mobile_number,
                              dp_rm_name,
                              fav_base_sqldate AS snapshot_date
   FROM
     (SELECT "dp id" AS dp_id,
             "dp name" as dp_name,
             "dp mobile number" as dp_mobile_number,
             "dp rm name" as dp_rm_name,
             TRIM(agent_mapped) AS agent_mapped,
             "last call subdiposition " AS last_call_subdisposition,
             toberemoved,
             db.fav_base_sqldate,
             ROW_NUMBER() OVER (PARTITION BY "dp id"
                                ORDER BY sqldate DESC) AS rn
      FROM spectrum.lglc_appsheet_dp_v2
      CROSS JOIN date_bounds db
      WHERE "dp category" = 'Favourite'
        AND sqldate = db.fav_base_sqldate
        AND agent_mapped IS NOT NULL
        AND TRIM(agent_mapped) <> ''
        AND TRIM(agent_mapped) NOT IN ('#N/A',
                                       '#REF!',
                                       '#N/A#REF!',
                                       'ambesh.gaunker@turtlemint.com')
        AND TRIM(agent_mapped) NOT LIKE '#%' ) t
   WHERE rn = 1
     AND (last_call_subdisposition IS NULL
          OR TRIM(last_call_subdisposition) NOT IN ('Remove from CRM Forever',
                                                    'DP-does-not-need-assistance',
                                                    'Remove Until New Quote Created'))
     AND (toberemoved IS NULL
          OR TRIM(UPPER(toberemoved)) NOT IN ('TRUE',
                                              'TRAINING',
                                              'UI-HIDDEN',
                                              'EXP_HIDDEN',
                                              'EXP2_HIDDEN'))) AS virtual_table;
"""
        fav_output_filename = f"query_fav_{data_date_str}.sql"
        with open(fav_output_filename, "w") as f:
            f.write(fav_query)

        # 8. Generate & Save Inactive Supply Query
        inactive_query = f"""WITH target_params AS (
    -- Sets target to data date for MTD calculations
    SELECT CAST('{data_date_str}' AS DATE) AS target_date
),
latest_dp_details AS (
    SELECT dp."dp id" AS dp_id,
           dp.agent_mapped,
           dp."dp category" AS dp_category,
           dp.source,
           dp.sqldate,
           dp.toberemoved,
           ROW_NUMBER() OVER (
               PARTITION BY dp."dp id"
               ORDER BY COALESCE(
                   TRY(CAST(dp.sqldate AS DATE)), 
                   TRY(date_parse(split_part(trim(dp.sqldate), ' ', 1), '%m/%d/%Y')), 
                   TRY(date_parse(split_part(trim(dp.sqldate), ' ', 1), '%d/%m/%Y'))
               ) DESC
           ) AS rn
    FROM spectrum.lglc_appsheet_dp_v2 dp
    CROSS JOIN target_params p
    WHERE dp.agent_mapped IS NOT NULL
      AND COALESCE(TRY(CAST(dp.sqldate AS DATE)), TRY(date_parse(split_part(trim(dp.sqldate), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(dp.sqldate), ' ', 1), '%d/%m/%Y'))) <= p.target_date 
),
eligible_dps AS (
    SELECT dp_id,
           agent_mapped,
           dp_category,
           sqldate
    FROM latest_dp_details
    WHERE rn = 1
      AND (toberemoved IS NULL OR TRIM(UPPER(toberemoved)) NOT IN ('TRUE', 'TRAINING', 'UI-HIDDEN', 'EXP_HIDDEN', 'EXP2_HIDDEN'))
      AND (source IS NULL OR TRIM(source) <> 'Referral-DP') 
),
dp_first_entry AS (
    SELECT dp_id,
           last_update_date AS first_sqldate
    FROM (
        SELECT qt."dp id" AS dp_id,
               COALESCE(TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%d/%m/%Y'))) AS last_update_date,
               ROW_NUMBER() OVER (
                   PARTITION BY qt."dp id"
                   ORDER BY COALESCE(TRY(date_parse(split_part(trim("Last Update Date "), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim("Last Update Date "), ' ', 1), '%d/%m/%Y'))) ASC
               ) AS rn
        FROM spectrum.lglc_appsheet_quotes_v2 qt
        CROSS JOIN target_params p
        WHERE "Last Update Date " IS NOT NULL
          AND trim("Last Update Date ") <> ''
          AND qt.stage = 'Sale-Done'
          AND CAST(COALESCE(TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%d/%m/%Y'))) AS DATE) <= p.target_date 
    ) filtered_quotes
    WHERE rn = 1 
),
quotes_created AS (
    SELECT *
    FROM (
        SELECT qt."quote id" AS quote_id,
               qt."dp id" AS dp_id,
               COALESCE(TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))) AS creation_ts,
               ROW_NUMBER() OVER (
                   PARTITION BY qt."quote id", CAST(COALESCE(TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))) AS DATE)
                   ORDER BY qt.stage DESC
               ) AS rn
        FROM spectrum.lglc_appsheet_quotes_v2 qt
        CROSS JOIN target_params p
        WHERE "creation date" IS NOT NULL
          AND trim("creation date") <> ''
          AND qt."quote id" IS NOT NULL
          AND LENGTH(TRIM(CAST(qt."quote id" AS VARCHAR))) <> 8
          -- MTD Logic: First of the month to data date
          AND CAST(COALESCE(TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))) AS DATE) >= DATE_TRUNC('month', p.target_date)
          AND CAST(COALESCE(TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))) AS DATE) <= p.target_date 
    ) filtered_quotes
    WHERE rn = 1 
),
quotes_agg_per_dp_month AS (
    -- Grabs the earliest quote date this month to ensure 1 row per DP
    SELECT dp_id,
           MIN(CAST(creation_ts AS DATE)) AS min_creation_date,
           date_trunc('month', CAST(MIN(creation_ts) AS DATE)) AS quote_month
    FROM quotes_created
    GROUP BY dp_id
),
dp_agent_quotes AS (
    SELECT qdp.dp_id,
           dps.agent_mapped,
           qdp.quote_month,
           qdp.min_creation_date,
           CASE
               WHEN dps.dp_category = 'Favourite' AND date_trunc('month', CAST(df.first_sqldate AS DATE)) = qdp.quote_month THEN 'Inactive'
               WHEN dps.dp_category = 'Favourite' THEN 'Favourite'
               ELSE 'Inactive'
           END AS category_type
    FROM quotes_agg_per_dp_month qdp
    LEFT JOIN eligible_dps dps ON qdp.dp_id = dps.dp_id
    LEFT JOIN dp_first_entry df ON qdp.dp_id = df.dp_id
)
SELECT DISTINCT 
    dp_id AS "dp id",
    agent_mapped AS "agent mapped",
    min_creation_date AS "date of entry"
FROM dp_agent_quotes
WHERE agent_mapped IS NOT NULL
  AND TRIM(agent_mapped) NOT IN ('#N/A', '#REF!', '#N/A#REF!')
  AND TRIM(agent_mapped) NOT LIKE '#%'
  -- Strictly filters for Inactive DPs based on the CASE statement logic
  AND category_type = 'Inactive'
ORDER BY "agent mapped", "date of entry";
"""
        inactive_output_filename = f"query_inactive_{data_date_str}.sql"
        with open(inactive_output_filename, "w") as f:
            f.write(inactive_query)

        print("-" * 30)
        if TARGET_MONTH:
            print(f"🔄 MODE: CATCH-UP ({TARGET_MONTH})")
        else:
            print(f"🚀 MODE: REGULAR")
            
        print(f"📅 Data Date Identified: {data_date_str}")
        print(f"📅 Status Threshold:    {first_date_of_data_month}")
        print(f"💾 Files Saved:")
        print(f"   • {output_filename}")
        print(f"   • {fav_output_filename}")
        print(f"   • {inactive_output_filename}")
        print("-" * 30)
        
        return query, output_filename

    except Exception as e:
        print(f"❌ Error generating query: {e}")
        return None, None

if __name__ == "__main__":
    generate_athena_query()