Conversion Rates Automation - Codebase Overview
The codebase is a sequential data processing, ETL (Extract, Transform, Load), and reporting pipeline orchestrating email attachments, SQL query generation, automated web browser interactions (Superset), data merging, and finally metrics computation.

The entire process is orchestrated sequentially by 
AutomateAll.py
.

1. System Flow & File Roles
The system processes a daily/monthly sales report file via an email attachment, cleans it up, generates necessary SQL lookups to fetch supplemental DP (Distribution Partner) data from Apache Superset, merges everything, and updates a trend tracker.

A. Master Orchestrator
AutomateAll.py
: The main entry point. It has two modes:
Manual Mode: User provides specific Subject Keywords and Date.
Auto-Run Mode:
Performs a "Gap Check": Inspects 
MTD_ConversionRate_Trend.xlsx
 to ensure the previous month had its end-of-month metrics fully run. If not, prompts for a 'catch-up' run.
Spawns subprocesses sequentially for the other 5 pipeline scripts via subprocess.run(), setting environment variables (TARGET_MONTH, SUBJECT_KEYWORD, RECEIVED_DATE) as configuration for downstream scripts.
B. The 5-Step Pipeline
SalesFileDownload.py
 (Data Extraction)

Connects to an IMAP server (imap.gmail.com).
Scans the inbox for an email from specific senders (istiyak.q9... or anant.dharme...) with attachments.
Saves the first identified Excel (
.xlsx
) sheet into ./downloads/. Use filters (Subject Keyword / target month) as passed by 
AutomateAll.py
.
SalesFileCleaning.py
 (Data Cleaning)

Loads the latest Excel file from ./downloads/.
Cleans the DP ID column inside the Health sheet (stripping string prefixes like "DP-").
Extracts unique DP IDs and saves them into a new dedicated sheet Health Unique DPs within the same Excel workbook.
QueryGenerator.py
 (SQL Generation)

Reads the parsed Health Unique DPs from the previous step.
Calculates the target dates based on the Excel file's data limit (important for Catch-up logic).
Generates an Amazon Athena SQL query string to aggregate policy count and check client_status (Active, Inactive, Activated by LGLC) from spectrum.policydetail.
Saves the SQL locally as query_YYYY-MM-DD.sql.
SupersetBot.py
 (Data Enrichment / UI Automation)

Utilizes playwright to automate browser interactions with Amazon / Apache Superset (https://insights.mintpro.in/sqllab/).
Reads the newly generated query_YYYY-MM-DD.sql and executes it in Superset to produce DP_Status_YYYY-MM-DD.csv.
Also runs two predefined SQL templates (FAV_DP_SQL_TEMPLATE and INACTIVE_SUPPLY_SQL_TEMPLATE) dynamically injected with target date macros.
Downloads all three resulting CSVs into ./downloads/.
MergeData.py
 (Data Consolidation)

Takes the output from Superset (DP_Status_YYYY-MM-DD.csv) and merges it back onto the original Excel file via DP ID / Key_ID mapping.
Fills nulls with "Inactive" fallback and leaves the raw status data inside a sheet called DP Status Data for auditing.
CalculateMetrics.py
 (Metrics & Tracking)

Reads the newly assembled unique DPs data and the Superset Denominator exports (InactiveSupply_...csv and Fav_DP_Count_...csv).
Handles BDM (Business Development Manager) mapping using raw mapping rules and fuzzy matching (thefuzz library) to match strings to emails.
Aggregates "Activation Rate," "Favourite Conv Rate," and "Consolidated Rate".
Appends a new metric row for this run into the tracker file: 
MTD_ConversionRate_Trend.xlsx
.
Dumps daily breakdown artifacts into Performance_Breakdown_YYYY-MM-DD.xlsx.
2. Shared Config / Important Directories
./downloads/: Scratchpad directory for transient excel sheets, downloaded csvs, and manipulated states between steps.
./superset_session/: Persistent chromium context used by playwright. Keeps session cookies to avoid re-authenticating Superset.
Environment variables: System state is cascaded via subprocess env vars rather than Python module importing or CLI argument parsing.
3. High-Level Dependency Graph
Email -> Python (imap_tools) -> Excel -> Python (pandas) -> SQL Text -> Python (playwright) -> Superset -> CSVs -> Python (pandas & thefuzz) -> Excel Trend Tracker
