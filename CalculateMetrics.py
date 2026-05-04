import pandas as pd
import os
import re
from thefuzz import fuzz
from datetime import datetime

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = './downloads'
BDM_COL_NAME = 'BDM Name'
TREND_TRACKER_FILE = 'MTD_ConversionRate_Trend.xlsx'

# Environment variables from Master Controller
TARGET_MONTH = os.getenv("TARGET_MONTH")
SUBJECT_KEYWORD = os.getenv("SUBJECT_KEYWORD")
RECEIVED_DATE = os.getenv("RECEIVED_DATE")

# Determine the Run Mode for logging and metadata
if SUBJECT_KEYWORD and RECEIVED_DATE:
    RUN_MODE = "MANUAL"
elif TARGET_MONTH:
    RUN_MODE = "CATCH-UP"
else:
    RUN_MODE = "REGULAR"

# --- MANUAL OVERRIDES & TEAM MAP ---
MANUAL_OVERRIDES = {'ALI ABBAS': 'ali.sayyed@turtlemint.com'}
TEAM_MAP = {
    'ajay.tank@turtlemint.com': 'old', 'surendra.rathod1@turtlemint.com': 'old',
    'nitin.mane1@turtlemint.com': 'old', 'sonam.yadav3@turtlemint.com': 'old',
    'pooja.bachche@turtlemint.com': 'old', 'mithilesh.yadav1@turtlemint.com': 'old',
    'prem.ughrejiya@turtlemint.com': 'new', 'kiran.hande1@turtlemint.com': 'old',
    'nitinkumar.dubey@turtlemint.com': 'old', 'rahul.goad@turtlemint.com': 'old',
    'vijay.satpute@turtlemint.com': 'old', 'shraddha.chavan@turtlemint.com': 'old',
    'sanket.kadam2@turtlemint.com': 'old', 'avinash.j@turtlemint.com': 'old',
    'ali.sayyed@turtlemint.com': 'old', 'priyanka.yadav3@turtlemint.com': 'old',
    'manoj.kalla@turtlemint.com': 'old', 'g.vijay9@turtlemint.com': 'new',
    'shubham.v9@turtlemint.com': 'new', 'p.lakhan@turtlemint.com': 'new',
    'k.payal8@turtlemint.com': 'new', 'nandini.ram3@turtlemint.com': 'new',
    'praful.m9@turtlemint.com': 'new', 'b.ujwal9@turtlemint.com': 'new',
    'dhiraj.patil9@turtlemint.com': 'new', 'm.rajashree9@turtlemint.com': 'new',
    'd.rohit9@turtlemint.com': 'new', 'k.pratibha9@turtlemint.com': 'new',
    'nandini.d7@turtlemint.com': 'new', 'mohd.shaikh8@turtlemint.com': 'new',
    'sanoo.chauhan2@turtlemint.com': 'new', 'v.komal9@turtlemint.com': 'new',
    'ritu.kamble5@turtlemint.com': 'new', 's.nitin7@turtlemint.com': 'new'
}

# --- HELPERS ---
def clean_string(text):
    if not isinstance(text, str): return ""
    text = text.upper().strip()
    return ' '.join(re.sub(r'[^A-Z\s]', ' ', text).split())

def map_bdm_to_email(bdm_names, bdm_emails):
    final_mapping = {}
    processed_emails = [{'orig': e, 'clean': clean_string(e.split('@')[0])} for e in bdm_emails]
    for name in bdm_names:
        clean_name = clean_string(name)
        if clean_name in MANUAL_OVERRIDES:
            final_mapping[name] = MANUAL_OVERRIDES[clean_name]; continue
        best_match, highest_score = "Unmapped", 0
        for e_obj in processed_emails:
            score = fuzz.token_sort_ratio(clean_name, e_obj['clean'])
            if clean_name and e_obj['clean'] and clean_name[0] == e_obj['clean'][0]: score += 5
            if score > highest_score: highest_score, best_match = score, e_obj['orig']
        final_mapping[name] = best_match if highest_score > 55 else "Unmapped"
    return final_mapping

# --- MAIN WORKFLOW ---
def run_metrics_workflow():
    all_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if not f.startswith('~$')]
    excel_files = [f for f in all_files if f.endswith(('.xlsx', '.xls'))]
    
    if not excel_files:
        print("❌ No Excel files found to process."); return

    latest_excel = max(excel_files, key=os.path.getctime)
    
    # Identify Target Date from 'Health' sheet
    df_date = pd.read_excel(latest_excel, sheet_name='Health', engine='openpyxl')
    data_date = pd.to_datetime(df_date['Date']).max().strftime('%Y-%m-%d')
    
    print(f"\n📈 Calculating Metrics | Mode: {RUN_MODE} | Date: {data_date}")

    # Load specific date-stamped CSVs
    inactive_csv = os.path.join(DOWNLOAD_FOLDER, f"InactiveSupply_{data_date}.csv")
    fav_csv = os.path.join(DOWNLOAD_FOLDER, f"Fav_DP_Count_{data_date}.csv")

    if not os.path.exists(inactive_csv) or not os.path.exists(fav_csv):
        print(f"❌ Denominator CSVs for {data_date} missing. Metrics skipped."); return

    df_unique = pd.read_excel(latest_excel, sheet_name='Health Unique DPs', engine='openpyxl')
    df_inactive_csv = pd.read_csv(inactive_csv)
    df_fav_csv = pd.read_csv(fav_csv)

    # Aggregations
    df_unique[BDM_COL_NAME] = df_unique[BDM_COL_NAME].apply(clean_string)
    bdm_to_email_map = map_bdm_to_email(df_unique[BDM_COL_NAME].dropna().unique(), list(TEAM_MAP.keys()))
    df_unique['Email'] = df_unique[BDM_COL_NAME].map(bdm_to_email_map)

    df_email = df_unique.groupby('Email').agg(
        Act_Num=('DP Status', lambda x: (x == 'Inactive').sum()),
        Fav_Num=('DP Status', lambda x: x.isin(['Activated by LGLC', 'Already Active']).sum()),
        Con_Num=('DP Status', 'count')
    ).reset_index()

    df_email['Act_Den'] = df_email['Email'].map(df_inactive_csv.groupby('agent_mapped')['sum_inactive_dps_creating_quotes'].sum()).fillna(0)
    df_email['Fav_Den'] = df_email['Email'].map(df_fav_csv.groupby('agent_mapped')['dp_count'].sum()).fillna(0)
    df_email['Con_Den'] = df_email['Act_Den'] + df_email['Fav_Den']

    # Final Overall Row
    act_n, act_d = df_email['Act_Num'].sum(), df_email['Act_Den'].sum()
    fav_n, fav_d = df_email['Fav_Num'].sum(), df_email['Fav_Den'].sum()
    con_n, con_d = df_email['Con_Num'].sum(), df_email['Con_Den'].sum()

    new_trend_row = {
        'Date': data_date,
        'Act Numerator': act_n, 'Act Denominator': act_d, 'Activation Rate': act_n/act_d if act_d > 0 else 0,
        'Fav Numerator': fav_n, 'Fav Denominator': fav_d, 'Favourite Conv Rate': fav_n/fav_d if fav_d > 0 else 0,
        'Consolidated Numerator': con_n, 'Consolidated Denominator': con_d, 'Consolidated Rate': con_n/con_d if con_d > 0 else 0,
        'Run Mode': RUN_MODE,
        'Run Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
    }

    # Update Trend Tracker
    if os.path.exists(TREND_TRACKER_FILE):
        df_trend = pd.read_excel(TREND_TRACKER_FILE)
        df_trend = pd.concat([df_trend[df_trend['Date'] != data_date], pd.DataFrame([new_trend_row])], ignore_index=True)
    else:
        df_trend = pd.DataFrame([new_trend_row])
    df_trend.sort_values(by='Date').to_excel(TREND_TRACKER_FILE, index=False)

    # Output Detailed Breakdown
    output_file = f"Performance_Breakdown_{data_date}.xlsx"
    with pd.ExcelWriter(output_file) as writer:
        pd.DataFrame([new_trend_row]).to_excel(writer, sheet_name='Summary (Mode-{} )'.format(RUN_MODE), index=False)
        df_email.to_excel(writer, sheet_name='Email Level', index=False)

    print(f"✅ Metrics Created in {RUN_MODE} mode for {data_date}.")

if __name__ == "__main__":
    run_metrics_workflow()