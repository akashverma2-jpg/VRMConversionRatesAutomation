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
SELECT 
    agent_mapped,
    team,
    COUNT("dp id") AS dp_count
FROM (
    SELECT 
        agent_mapped,
        "dp id",
        CASE 
            WHEN agent_mapped IN ('ajay.tank@turtlemint.com','surendra.rathod1@turtlemint.com','nitin.mane1@turtlemint.com','sonam.yadav3@turtlemint.com','pooja.bachche@turtlemint.com','mithilesh.yadav1@turtlemint.com','kiran.hande1@turtlemint.com','nitinkumar.dubey@turtlemint.com','rahul.goad@turtlemint.com','vijay.satpute@turtlemint.com','shraddha.chavan@turtlemint.com','sanket.kadam2@turtlemint.com','avinash.j@turtlemint.com','ali.sayyed@turtlemint.com','priyanka.yadav3@turtlemint.com','manoj.kalla@turtlemint.com','gulshan.s1@turtlemint.com','maurya.vishal1@turtlemint.com','sonam.p1@turtlemint.com') THEN 'old'
            WHEN agent_mapped IN ('prem.ughrejiya@turtlemint.com','g.vijay9@turtlemint.com','shubham.v9@turtlemint.com','p.lakhan@turtlemint.com','k.payal8@turtlemint.com','nandini.ram3@turtlemint.com','praful.m9@turtlemint.com','b.ujwal9@turtlemint.com','dhiraj.patil9@turtlemint.com','m.rajashree9@turtlemint.com','d.rohit9@turtlemint.com','k.pratibha9@turtlemint.com','nandini.d7@turtlemint.com','mohd.shaikh8@turtlemint.com','sanoo.chauhan2@turtlemint.com','v.komal9@turtlemint.com','ritu.kamble5@turtlemint.com','s.nitin7@turtlemint.com','satish.k1@turtlemint.com','naresh.k1@turtlemint.com','g.vijay9@turtlemint.com','pranali.m1@turtlemint.com') THEN 'new'
            ELSE 'unknown'
        END AS team
    FROM spectrum.lglc_appsheet_dp_v2
    WHERE "dp category" = 'Favourite'
      AND "last call subdiposition " not in ('Remove from CRM Forever','DP-does-not-need-assistance') 
      AND sqldate = date_format(date_add('day', -1, date_trunc('month', {{DATE_REF}})), '%Y-%m-%d')
) t
GROUP BY agent_mapped, team;
"""

INACTIVE_SUPPLY_SQL_TEMPLATE = """
SELECT 
    date_trunc('month', CAST(quote_month AS TIMESTAMP)) AS quote_month,
    agent_mapped,
    SUM(inactive_dps_creating_quotes) AS sum_inactive_dps_creating_quotes
FROM
(
    WITH quotes_created AS
    (
        SELECT *
        FROM
        (
            SELECT 
                qt."quote id" AS quote_id,
                qt."dp id" AS dp_id,
                COALESCE(
                    TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')),
                    TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))
                ) AS creation_ts,
                qt.stage,
                ROW_NUMBER() OVER (
                    PARTITION BY qt."quote id",
                    CAST(
                        COALESCE(
                            TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')),
                            TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))
                        ) AS DATE
                    )
                    ORDER BY qt.stage DESC
                ) AS rn
            FROM spectrum.lglc_appsheet_quotes_v2 qt
            WHERE "creation date" IS NOT NULL
              AND trim("creation date") <> ''
              AND CAST(
                    COALESCE(
                        TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')),
                        TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))
                    ) AS DATE
                  ) BETWEEN date_trunc('month', {{DATE_REF}}) AND {{DATE_REF}}
        ) filtered_quotes
        WHERE rn = 1
    ),
    quotes_agg_per_dp_month AS
    (
        SELECT 
            dp_id,
            date_trunc('month', CAST(creation_ts AS DATE)) AS quote_month,
            COUNT(*) AS quotes_count
        FROM quotes_created
        GROUP BY dp_id, date_trunc('month', CAST(creation_ts AS DATE))
    ),
    dp_details_dedup AS
    (
        SELECT * FROM (
            SELECT dp."dp id" AS dp_id, dp.agent_mapped, dp."dp category" AS dp_category, dp.sqldate,
            ROW_NUMBER() OVER (PARTITION BY dp."dp id" ORDER BY dp.sqldate DESC) AS rn
            FROM spectrum.lglc_appsheet_dp_v2 dp WHERE dp.agent_mapped IS NOT NULL
        ) t WHERE rn = 1
    ),
    dp_first_entry AS
    (
        SELECT dp_id, last_update_date AS first_sqldate FROM (
            SELECT qt."dp id" AS dp_id, 
            COALESCE(TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%m/%d/%Y')), TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%d/%m/%Y'))) AS last_update_date,
            ROW_NUMBER() OVER (PARTITION BY qt."dp id" ORDER BY 2 ASC) AS rn
            FROM spectrum.lglc_appsheet_quotes_v2 qt WHERE "Last Update Date " IS NOT NULL AND qt.stage = 'Sale-Done'
        ) filtered_quotes WHERE rn = 1
    ),
    dp_agent_quotes AS
    (
        SELECT 
            qdp.dp_id, dps.agent_mapped, qdp.quote_month, qdp.quotes_count,
            CASE
                WHEN dps.dp_category = 'Favourite' AND date_trunc('month', CAST(df.first_sqldate AS DATE)) = qdp.quote_month THEN 'Inactive'
                WHEN dps.dp_category = 'Favourite' THEN 'Favourite'
                ELSE 'Inactive'
            END AS category_type
        FROM quotes_agg_per_dp_month qdp
        LEFT JOIN dp_details_dedup dps ON qdp.dp_id = dps.dp_id
        LEFT JOIN dp_first_entry df ON qdp.dp_id = df.dp_id
        WHERE qdp.quote_month = date_trunc('month', {{DATE_REF}})
    )
    SELECT agent_mapped, quote_month, COUNT(DISTINCT dp_id) AS inactive_dps_creating_quotes
    FROM dp_agent_quotes
    WHERE agent_mapped IS NOT NULL AND category_type = 'Inactive'
    GROUP BY agent_mapped, quote_month
) AS virtual_table
GROUP BY 1, 2
"""

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

def get_source_file_info():
    files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) 
             if f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')]
    if not files: return None, None
    
    target_month = get_target_month_name().lower()
    filtered_files = [f for f in files if target_month in os.path.basename(f).lower()]
    
    if filtered_files:
        latest_excel = max(filtered_files, key=os.path.getmtime)
    else:
        latest_excel = max(files, key=os.path.getmtime)
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

    # Pre-process Denominator SQLs
    processed_inactive_sql = prepare_sql(INACTIVE_SUPPLY_SQL_TEMPLATE, data_date)
    processed_fav_sql = prepare_sql(FAV_DP_SQL_TEMPLATE, data_date)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(SESSION_DIR, headless=False)
        page = context.pages[0]
        page.goto(URL)
        page.wait_for_url("**/sqllab/**", timeout=0)
        
        # Sequentially process all three downloads
        run_query_and_download(page, dp_status_sql, status_csv)
        run_query_and_download(page, processed_inactive_sql, inactive_csv)
        run_query_and_download(page, processed_fav_sql, fav_dp_csv)

        context.close()
        print("\n🏁 Automation Finished.")

if __name__ == "__main__":
    run_automation()