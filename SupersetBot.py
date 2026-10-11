import os
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime
import re

# --- CONFIG ---
URL = "https://insights.mintpro.in/sqllab/"
DOWNLOAD_FOLDER = './downloads'
SESSION_DIR = "./superset_session"
TARGET_MONTH = os.getenv("TARGET_MONTH") 

# --- SQL TEMPLATES ---
FAV_DP_SQL_TEMPLATE = """
SELECT dp_id AS dp_id,
       agent_mapped AS agent_mapped,
       dp_name AS dp_name,
       dp_mobile_number AS dp_mobile_number,
       dp_rm_name AS dp_rm_name,
       snapshot_date AS snapshot_date
FROM
  (WITH config AS
     (SELECT 0 AS month_offset),
        date_bounds AS
     (SELECT date_add('month', -cfg.month_offset, date_trunc('month', {{DATE_REF}})) AS target_month_start,
             date_format(date_add('day', -1, date_add('month', -cfg.month_offset, date_trunc('month', {{DATE_REF}}))), '%Y-%m-%d') AS fav_base_sqldate
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

INACTIVE_SUPPLY_SQL_TEMPLATE = """
WITH target_params AS (
    -- Sets target to data date for MTD calculations
    SELECT CAST({{DATE_REF}} AS DATE) AS target_date
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

from PipelineUtils import get_target_sales_file, get_target_month_name

def get_source_file_info():
    latest_excel = get_target_sales_file(DOWNLOAD_FOLDER)
    if not latest_excel:
        return None, None
    df = pd.read_excel(latest_excel, sheet_name='Health', engine='openpyxl')
    max_date = pd.to_datetime(df['Date']).max()
    return latest_excel, max_date.strftime('%Y-%m-%d')

def prepare_sql(template, data_date):
    date_ref = f"CAST('{data_date}' AS DATE)"
    return template.replace("{{DATE_REF}}", date_ref)

def run_query_and_download(page, sql_text, target_filename):
    """ACTUAL DEFINITION of UI Automation logic."""
    print(f"\n--- Processing: {target_filename} ---")
    
    # 1. Create a new tab to avoid clobbering the current one
    try:
        page.locator('[aria-label="plus-circle"], .fa-plus, .sqllab-add-tab').first.click()
        page.wait_for_timeout(1000)
    except:
        page.click("text='Add Tab'")

    # 2. Inject Query into Ace Editor
    page.wait_for_selector(".ace_editor")
    page.evaluate("(text) => { ace.edit(document.querySelector('.ace_editor')).setValue(text); }", sql_text)

    # 3. Trigger Query
    page.locator('button:has-text("RUN")').first.click()
    print("🚀 Query triggered. Waiting for results...")

    # 4. Monitor and Download (Timeout extended to 10 mins)
    download_selector = page.get_by_text(re.compile("DOWNLOAD TO CSV", re.IGNORECASE))
    download_selector.wait_for(state="visible", timeout=600000) 
    
    with page.expect_download() as download_info:
        download_selector.click()
    
    download = download_info.value
    final_path = os.path.join(DOWNLOAD_FOLDER, target_filename)
    download.save_as(final_path)
    print(f"✅ Downloaded: {target_filename}")

def run_automation():
    source_file, data_date = get_source_file_info()
    if not data_date: return

    print(f"📅 Running Superset for Data Date: {data_date}")

    status_csv = f"DP_Status_{data_date}.csv"
    inactive_csv = f"InactiveSupply_{data_date}.csv"
    fav_dp_csv = f"Fav_DP_Count_{data_date}.csv"
    
    # Identify the query file generated by QueryGenerator.py
    query_file = f"query_{data_date}.sql"
    if not os.path.exists(query_file):
        print(f"❌ Error: {query_file} missing. Did QueryGenerator run first?")
        return

    with open(query_file, "r") as f: 
        dp_status_sql = f.read()

    # Pre-process Denominator SQLs (prioritize generated files from QueryGenerator, else fallback to template)
    fav_query_file = f"query_fav_{data_date}.sql"
    inact_query_file = f"query_inactive_{data_date}.sql"

    if os.path.exists(fav_query_file):
        with open(fav_query_file, "r") as f:
            processed_fav_sql = f.read()
    else:
        processed_fav_sql = prepare_sql(FAV_DP_SQL_TEMPLATE, data_date)

    if os.path.exists(inact_query_file):
        with open(inact_query_file, "r") as f:
            processed_inactive_sql = f.read()
    else:
        processed_inactive_sql = prepare_sql(INACTIVE_SUPPLY_SQL_TEMPLATE, data_date)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(SESSION_DIR, headless=False)
        page = context.pages[0]
        page.goto(URL)
        print("⏳ Waiting for Superset SQL Lab to load (if prompted to log in, please complete login in the browser)...")
        page.wait_for_url("**/sqllab/**", timeout=0)
        page.wait_for_selector(".ace_editor", timeout=0)
        page.wait_for_timeout(2000)
        print("✅ Superset SQL Lab ready!")
        
        # Sequentially process all three downloads
        run_query_and_download(page, dp_status_sql, status_csv)
        run_query_and_download(page, processed_inactive_sql, inactive_csv)
        run_query_and_download(page, processed_fav_sql, fav_dp_csv)

        context.close()
        print("\n🏁 Automation Finished.")

if __name__ == "__main__":
    run_automation()