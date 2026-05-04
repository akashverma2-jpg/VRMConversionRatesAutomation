import os
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime

# --- CONFIG ---
URL = "https://insights.mintpro.in/sqllab/"
DOWNLOAD_FOLDER = './downloads'
SESSION_DIR = "./superset_session"

# --- TARGET DATE DISCOVERY ---
def get_target_date_from_excel():
    """Finds the latest Excel and identifies the data date from the 'Health' sheet."""
    files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) 
             if f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')]
    
    if not files:
        return None, None
    
    latest_file = max(files, key=os.path.getctime)
    df = pd.read_excel(latest_file, sheet_name='Health', engine='openpyxl')
    max_date = pd.to_datetime(df['Date']).max().strftime('%Y-%m-%d')
    return latest_file, max_date

def run_query_and_download(page, sql_query, target_filename):
    """Automation logic to paste SQL, run, and download CSV."""
    # (Existing logic for interacting with Superset UI goes here)
    # 1. Clear editor and paste sql_query
    # 2. Click 'Run'
    # 3. Wait for results and click 'Download to CSV'
    # 4. Save the file as target_filename in DOWNLOAD_FOLDER
    pass

def run_automation():
    # 1. Identify the Date from the source file
    source_file, data_date = get_target_date_from_excel()
    if not data_date:
        print("❌ No source data found to determine query date.")
        return

    print(f"🤖 SupersetBot: Targeting data for {data_date}")

    # 2. Define the 3 Target CSVs (Now date-specific)
    status_csv = f"DP_Status_{data_date}.csv"
    inactive_csv = f"InactiveSupply_{data_date}.csv"
    fav_dp_csv = f"Fav_DP_Count_{data_date}.csv"

    # 3. Read the Query generated in the previous step
    query_file = f"query_{data_date}.sql"
    if not os.path.exists(query_file):
        print(f"❌ SQL file {query_file} not found. Ensure QueryGenerator ran first.")
        return

    with open(query_file, "r") as f:
        dp_status_sql = f.read()

    # --- INACTIVE SUPPLY & FAV DP SQL (Fixed/Static Queries) ---
    # These queries remain the same but their output is saved with the data_date
    INACTIVE_SUPPLY_SQL = """
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
                AND (
                        TRY(date_parse(split_part(trim("creation date"), ' ', 1), '%m/%d/%Y')) IS NOT NULL
                    OR TRY(date_parse(split_part(trim("creation date"), ' ', 1), '%d/%m/%Y')) IS NOT NULL
                )
                AND CAST(
                        COALESCE(
                            TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%m/%d/%Y')),
                            TRY(date_parse(split_part(trim(qt."creation date"), ' ', 1), '%d/%m/%Y'))
                        ) AS DATE
                    ) BETWEEN date_trunc('month', current_date) AND current_date
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
            SELECT *
            FROM
            (
                SELECT 
                    dp."dp id" AS dp_id,
                    dp.agent_mapped,
                    dp."dp category" AS dp_category,
                    dp.sqldate,
                    ROW_NUMBER() OVER (
                        PARTITION BY dp."dp id"
                        ORDER BY dp.sqldate DESC
                    ) AS rn
                FROM spectrum.lglc_appsheet_dp_v2 dp
                WHERE dp.agent_mapped IS NOT NULL
            ) t
            WHERE rn = 1
        ),
        dp_first_entry AS
        (
            SELECT dp_id, last_update_date AS first_sqldate
            FROM
            (
                SELECT 
                    qt."dp id" AS dp_id,
                    COALESCE(
                        TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%m/%d/%Y')),
                        TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%d/%m/%Y'))
                    ) AS last_update_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY qt."dp id"
                        ORDER BY COALESCE(
                            TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%m/%d/%Y')),
                            TRY(date_parse(split_part(trim(qt."Last Update Date "), ' ', 1), '%d/%m/%Y'))
                        ) ASC
                    ) AS rn
                FROM spectrum.lglc_appsheet_quotes_v2 qt
                WHERE "Last Update Date " IS NOT NULL
                AND trim("Last Update Date ") <> ''
                AND (
                        TRY(date_parse(split_part(trim("Last Update Date "), ' ', 1), '%m/%d/%Y')) IS NOT NULL
                    OR TRY(date_parse(split_part(trim("Last Update Date "), ' ', 1), '%d/%m/%Y')) IS NOT NULL
                )
                AND qt.stage = 'Sale-Done'
            ) filtered_quotes
            WHERE rn = 1
        ),
        dp_agent_quotes AS
        (
            SELECT 
                qdp.dp_id,
                dps.agent_mapped,
                qdp.quote_month,
                qdp.quotes_count,
                CASE
                    WHEN dps.dp_category = 'Favourite'
                        AND date_trunc('month', CAST(df.first_sqldate AS DATE)) = qdp.quote_month THEN 'Inactive'
                    WHEN dps.dp_category = 'Favourite' THEN 'Favourite'
                    ELSE 'Inactive'
                END AS category_type
            FROM quotes_agg_per_dp_month qdp
            LEFT JOIN dp_details_dedup dps ON qdp.dp_id = dps.dp_id
            LEFT JOIN dp_first_entry df ON qdp.dp_id = df.dp_id
            WHERE qdp.quote_month = date_trunc('month', current_date)
        )
        SELECT 
            agent_mapped,
            quote_month,
            COUNT(DISTINCT dp_id) AS inactive_dps_creating_quotes
        FROM dp_agent_quotes
        WHERE agent_mapped IS NOT NULL
        AND agent_mapped NOT IN ('#N/A', '#REF!')
        AND category_type = 'Inactive'
        GROUP BY agent_mapped, quote_month
    ) AS virtual_table
    GROUP BY 
        date_trunc('month', CAST(quote_month AS TIMESTAMP)),
        agent_mapped
    ORDER BY sum_inactive_dps_creating_quotes DESC
    LIMIT 10000;
"""
    FAV_DP_SQL = """
    SELECT 
        agent_mapped,
        team,
        COUNT("dp id") AS dp_count
    FROM (
        SELECT 
            agent_mapped,
            "dp id",
            CASE 
                WHEN agent_mapped IN ('ajay.tank@turtlemint.com','surendra.rathod1@turtlemint.com','nitin.mane1@turtlemint.com','sonam.yadav3@turtlemint.com','pooja.bachche@turtlemint.com','mithilesh.yadav1@turtlemint.com','kiran.hande1@turtlemint.com','nitinkumar.dubey@turtlemint.com','rahul.goad@turtlemint.com','vijay.satpute@turtlemint.com','shraddha.chavan@turtlemint.com','sanket.kadam2@turtlemint.com','avinash.j@turtlemint.com','ali.sayyed@turtlemint.com','priyanka.yadav3@turtlemint.com','manoj.kalla@turtlemint.com') THEN 'old'
                WHEN agent_mapped IN ('prem.ughrejiya@turtlemint.com','g.vijay9@turtlemint.com','shubham.v9@turtlemint.com','p.lakhan@turtlemint.com','k.payal8@turtlemint.com','nandini.ram3@turtlemint.com','praful.m9@turtlemint.com','b.ujwal9@turtlemint.com','dhiraj.patil9@turtlemint.com','m.rajashree9@turtlemint.com','d.rohit9@turtlemint.com','k.pratibha9@turtlemint.com','nandini.d7@turtlemint.com','mohd.shaikh8@turtlemint.com','sanoo.chauhan2@turtlemint.com','v.komal9@turtlemint.com','ritu.kamble5@turtlemint.com','s.nitin7@turtlemint.com') THEN 'new'
                ELSE 'unknown'
            END AS team
        FROM spectrum.lglc_appsheet_dp_v2
        WHERE "dp category" = 'Favourite'
        AND "last call disposition" NOT IN ('Remap-DP')
        AND sqldate = date_format(date_add('day', -1, date_trunc('month', current_date)), '%Y-%m-%d')
    ) t
    GROUP BY agent_mapped, team;
"""
    # 4. Execute Automation via Playwright
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(SESSION_DIR, headless=False)
        page = context.pages[0]
        page.goto(URL)
        
        # Ensure login/navigation is successful
        page.wait_for_selector(".sql-editor", timeout=0)

        # Run Task 1: DP Status (Main Query)
        print(f"⏳ Running DP Status Query for {data_date}...")
        run_query_and_download(page, dp_status_sql, status_csv)

        # Run Task 2: Inactive Supply
        print(f"⏳ Running Inactive Supply Query...")
        run_query_and_download(page, INACTIVE_SUPPLY_SQL, inactive_csv)

        # Run Task 3: Favourite DP Count
        print(f"⏳ Running Favourite DP Count Query...")
        run_query_and_download(page, FAV_DP_SQL, fav_dp_csv)

        context.close()
        print(f"✅ All 3 CSVs downloaded for {data_date}")

if __name__ == "__main__":
    run_automation()