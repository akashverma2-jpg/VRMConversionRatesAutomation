import pandas as pd
import os
import re
from thefuzz import fuzz
from datetime import datetime

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = './downloads'
BDM_COL_NAME = 'BDM Name'
TREND_TRACKER_FILE = 'MTD_ConversionRate_Trend.xlsx'

# --- MANUAL OVERRIDES ---
MANUAL_OVERRIDES = {
    'ALI ABBAS': 'ali.sayyed@turtlemint.com',
}

# --- TEAM MAP ---
TEAM_MAP = {
    'ajay.tank@turtlemint.com': 'old',
    'surendra.rathod1@turtlemint.com': 'old',
    'nitin.mane1@turtlemint.com': 'old',
    'sonam.yadav3@turtlemint.com': 'old',
    'pooja.bachche@turtlemint.com': 'old',
    'mithilesh.yadav1@turtlemint.com': 'old',
    'prem.ughrejiya@turtlemint.com': 'new',
    'kiran.hande1@turtlemint.com': 'old',
    'nitinkumar.dubey@turtlemint.com': 'old',
    'rahul.goad@turtlemint.com': 'old',
    'vijay.satpute@turtlemint.com': 'old',
    'shraddha.chavan@turtlemint.com': 'old',
    'sanket.kadam2@turtlemint.com': 'old',
    'avinash.j@turtlemint.com': 'old',
    'ali.sayyed@turtlemint.com': 'old',
    'priyanka.yadav3@turtlemint.com': 'old',
    'manoj.kalla@turtlemint.com': 'old',
    'g.vijay9@turtlemint.com': 'new',
    'shubham.v9@turtlemint.com': 'new',
    'p.lakhan@turtlemint.com': 'new',
    'k.payal8@turtlemint.com': 'new',
    'nandini.ram3@turtlemint.com': 'new',
    'praful.m9@turtlemint.com': 'new',
    'b.ujwal9@turtlemint.com': 'new',
    'dhiraj.patil9@turtlemint.com': 'new',
    'm.rajashree9@turtlemint.com': 'new',
    'd.rohit9@turtlemint.com': 'new',
    'k.pratibha9@turtlemint.com': 'new',
    'nandini.d7@turtlemint.com': 'new',
    'mohd.shaikh8@turtlemint.com': 'new',
    'sanoo.chauhan2@turtlemint.com': 'new',
    'v.komal9@turtlemint.com': 'new',
    'ritu.kamble5@turtlemint.com': 'new',
    's.nitin7@turtlemint.com': 'new'
}

# --- HELPERS ---
def clean_string(text):
    if not isinstance(text, str):
        return ""
    text = text.upper().strip()
    text = re.sub(r'[^A-Z\s]', ' ', text)
    return ' '.join(text.split())

def map_bdm_to_email(bdm_names, bdm_emails):
    final_mapping = {}

    processed_emails = [
        {'orig': e, 'clean': clean_string(e.split('@')[0])}
        for e in bdm_emails
    ]

    for name in bdm_names:
        clean_name = clean_string(name)

        if clean_name in MANUAL_OVERRIDES:
            final_mapping[name] = MANUAL_OVERRIDES[clean_name]
            continue

        best_match, highest_score = "Unmapped", 0

        for e_obj in processed_emails:
            score = fuzz.token_sort_ratio(clean_name, e_obj['clean'])

            if clean_name and e_obj['clean'] and clean_name[0] == e_obj['clean'][0]:
                score += 5

            if score > highest_score:
                highest_score, best_match = score, e_obj['orig']

        final_mapping[name] = best_match if highest_score > 55 else "Unmapped"

    return final_mapping


# --- MAIN WORKFLOW ---
def run_metrics_workflow():

    # Load latest files
    all_files = [os.path.join(DOWNLOAD_FOLDER, f) for f in os.listdir(DOWNLOAD_FOLDER) if not f.startswith('~$')]

    latest_excel = max([f for f in all_files if f.endswith(('.xlsx', '.xls'))], key=os.path.getctime)
    latest_inactive_csv = max([f for f in all_files if 'InactiveSupply' in f], key=os.path.getctime)
    latest_fav_csv = max([f for f in all_files if 'Fav_DP_Count' in f], key=os.path.getctime)

    df_unique = pd.read_excel(latest_excel, sheet_name='Health Unique DPs', engine='openpyxl')
    df_inactive_csv = pd.read_csv(latest_inactive_csv)
    df_fav_csv = pd.read_csv(latest_fav_csv)

    # --- CLEAN BDM NAMES ---
    df_unique[BDM_COL_NAME] = df_unique[BDM_COL_NAME].apply(clean_string)

    # --- MAP EMAIL ---
    unique_bdms = df_unique[BDM_COL_NAME].dropna().unique()
    bdm_to_email_map = map_bdm_to_email(unique_bdms, list(TEAM_MAP.keys()))

    df_unique['Email'] = df_unique[BDM_COL_NAME].map(bdm_to_email_map)

    # --- NUMERATOR (EMAIL LEVEL) ---
    df_email = df_unique.groupby('Email').agg(
        Act_Num=('DP Status', lambda x: (x == 'Inactive').sum()),
        Fav_Num=('DP Status', lambda x: x.isin(['Activated by LGLC', 'Already Active']).sum()),
        Con_Num=('DP Status', 'count')
    ).reset_index()

    # --- DENOMINATOR (ALREADY EMAIL LEVEL) ---
    act_den_map = df_inactive_csv.groupby('agent_mapped')['sum_inactive_dps_creating_quotes'].sum()
    fav_den_map = df_fav_csv.groupby('agent_mapped')['dp_count'].sum()

    df_email['Act_Den'] = df_email['Email'].map(act_den_map).fillna(0)
    df_email['Fav_Den'] = df_email['Email'].map(fav_den_map).fillna(0)
    df_email['Con_Den'] = df_email['Act_Den'] + df_email['Fav_Den']

    # --- RATES ---
    df_email['Act_Rate'] = df_email['Act_Num'] / df_email['Act_Den'].replace(0, 1)
    df_email['Fav_Rate'] = df_email['Fav_Num'] / df_email['Fav_Den'].replace(0, 1)
    df_email['Con_Rate'] = df_email['Con_Num'] / df_email['Con_Den'].replace(0, 1)

    # --- TEAM MAPPING ---
    df_email['Team'] = df_email['Email'].map(TEAM_MAP).fillna('Unknown')

    # --- TEAM AGGREGATION ---
    df_team = df_email.groupby('Team').agg({
        'Act_Num': 'sum',
        'Act_Den': 'sum',
        'Fav_Num': 'sum',
        'Fav_Den': 'sum',
        'Con_Num': 'sum',
        'Con_Den': 'sum'
    }).reset_index()

    df_team['Act_Rate'] = df_team['Act_Num'] / df_team['Act_Den'].replace(0, 1)
    df_team['Fav_Rate'] = df_team['Fav_Num'] / df_team['Fav_Den'].replace(0, 1)
    df_team['Con_Rate'] = df_team['Con_Num'] / df_team['Con_Den'].replace(0, 1)

    # --- OVERALL METRICS ---
    act_n = df_email['Act_Num'].sum()
    act_d = df_email['Act_Den'].sum()

    fav_n = df_email['Fav_Num'].sum()
    fav_d = df_email['Fav_Den'].sum()

    con_n = df_email['Con_Num'].sum()
    con_d = df_email['Con_Den'].sum()

    data_date = os.path.basename(latest_inactive_csv).split('_')[1].replace('.csv', '')

    new_trend_row = {
        'Date': data_date,
        'Act Numerator': act_n,
        'Act Denominator': act_d,
        'Activation Rate': act_n / act_d if act_d > 0 else 0,
        'Fav Numerator': fav_n,
        'Fav Denominator': fav_d,
        'Favourite Conv Rate': fav_n / fav_d if fav_d > 0 else 0,
        'Consolidated Numerator': con_n,
        'Consolidated Denominator': con_d,
        'Consolidated Rate': con_n / con_d if con_d > 0 else 0,
        'Run Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
    }

    # --- TREND FILE ---
    if os.path.exists(TREND_TRACKER_FILE):
        df_trend = pd.read_excel(TREND_TRACKER_FILE)
        df_trend = pd.concat([df_trend[df_trend['Date'] != data_date], pd.DataFrame([new_trend_row])], ignore_index=True)
    else:
        df_trend = pd.DataFrame([new_trend_row])

    df_trend.sort_values(by='Date').to_excel(TREND_TRACKER_FILE, index=False)

    # --- OUTPUT ---
    output_file = f"Performance_Breakdown_{data_date}.xlsx"

    with pd.ExcelWriter(output_file) as writer:
        pd.DataFrame([new_trend_row]).to_excel(writer, sheet_name='Aggregate Summary', index=False)
        df_team.to_excel(writer, sheet_name='Team Level', index=False)
        df_email.to_excel(writer, sheet_name='Email Level', index=False)

    print(f"\n✅ Fixed: No denominator double counting")
    print(f"✅ Output: {output_file}")


if __name__ == "__main__":
    run_metrics_workflow()