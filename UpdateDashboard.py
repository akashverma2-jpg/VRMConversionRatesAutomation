import pandas as pd
import json
import os
import re
import subprocess
import math
from datetime import datetime

# --- CONFIGURATION ---
TREND_FILE = 'MTD_ConversionRate_Trend.xlsx'
DASHBOARD_DIR = '/Users/akashverma/Documents/ConvAutomationAndReporting/vrm_mtd_conv_rates/vrm_mtd_conv_rates'
HTML_FILE = os.path.join(DASHBOARD_DIR, 'mtd_dashboard.html')

def clean_nans(obj):
    if isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj

def run_command(cmd, cwd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        print(f"⚠️ Warning running command in {cwd}: {cmd}\nError: {result.stderr}")
    return result

def main():
    if not os.path.exists(TREND_FILE):
        print(f"❌ Trend tracker file {TREND_FILE} not found. Cannot update dashboard.")
        return

    print("📊 Loading trend tracker data...")
    # Load sheet1 (metrics)
    try:
        df_trend = pd.read_excel(TREND_FILE, sheet_name='Sheet1')
    except Exception as e:
        print(f"❌ Error reading Sheet1 from {TREND_FILE}: {e}")
        return

    # Load targets sheet
    try:
        df_targets_raw = pd.read_excel(TREND_FILE, sheet_name='Targets')
    except Exception:
        df_targets_raw = pd.DataFrame(columns=['Month', 'Activation Target', 'Favourite Target', 'Consolidated Target'])

    if df_trend.empty:
        print("❌ Trend tracker sheet is empty. Nothing to update.")
        return

    df_trend['Date'] = pd.to_datetime(df_trend['Date'])
    df_trend['MonthStr'] = df_trend['Date'].dt.strftime('%Y-%m')
    df_trend['DayInt'] = df_trend['Date'].dt.day

    # Sort values to guarantee chronological order
    df_trend = df_trend.sort_values(by='Date')

    # Build targets dictionary
    targets = {}
    for _, row in df_targets_raw.iterrows():
        month = str(row['Month']).strip()
        targets[month] = {
            'cons': float(row['Consolidated Target']) if pd.notna(row['Consolidated Target']) else 9.0,
            'act': float(row['Activation Target']) if pd.notna(row['Activation Target']) else 2.5,
            'fav': float(row['Favourite Target']) if pd.notna(row['Favourite Target']) else 15.0
        }

    # Group daily records by month
    months_data = {}
    for month_str, group in df_trend.groupby('MonthStr'):
        # For any month without defined targets, assign defaults
        if month_str not in targets:
            targets[month_str] = {'cons': 9.0, 'act': 2.5, 'fav': 15.0}

        month_entries = []
        for _, row in group.iterrows():
            rate_val = row.get('Consolidated Rate', 0)
            if pd.isna(rate_val):
                rate_val = 0
            
            entry = {
                'day': int(row['DayInt']),
                'rate': round(float(rate_val) * 100, 4),
                'actNum': int(row['Act Numerator']) if pd.notna(row.get('Act Numerator')) else None,
                'actDen': int(row['Act Denominator']) if pd.notna(row.get('Act Denominator')) else None,
                'favNum': int(row['Fav Numerator']) if pd.notna(row.get('Fav Numerator')) else None,
                'favDen': int(row['Fav Denominator']) if pd.notna(row.get('Fav Denominator')) else None,
                'consNum': int(row['Consolidated Numerator']) if pd.notna(row.get('Consolidated Numerator')) else None,
                'consDen': int(row['Consolidated Denominator']) if pd.notna(row.get('Consolidated Denominator')) else None
            }
            month_entries.append(entry)
        
        # Sort days chronologically
        months_data[month_str] = sorted(month_entries, key=lambda x: x['day'])

    # Determine latest month as active month
    latest_month = df_trend['MonthStr'].iloc[-1]

    # Structure SEED payload
    seed_data = {
        'cur': latest_month,
        'scenario': 'base',
        'hist': 'none',
        'updatedAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'targets': targets,
        'months': months_data
    }

    # Clean NaNs and infinite floats
    seed_data = clean_nans(seed_data)
    seed_json_str = json.dumps(seed_data, separators=(',', ':'))

    # Update mtd_dashboard.html
    if not os.path.exists(HTML_FILE):
        print(f"❌ Dashboard HTML file not found at: {HTML_FILE}")
        return

    print(f"📝 Updating preloaded data in {HTML_FILE}...")
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Search for const SEED = ... and replace it
    pattern = r'const SEED\s*=\s*\{.*?\};'
    new_seed_line = f'const SEED = {seed_json_str};'
    
    if not re.search(pattern, html_content):
        print("❌ Could not find 'const SEED = {...};' pattern in the HTML file!")
        return

    updated_content = re.sub(pattern, new_seed_line, html_content)

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print("✅ Local dashboard HTML updated.")

    # Git deployment
    print("🚀 Committing and pushing changes to GitHub Pages repository...")
    run_command("git add mtd_dashboard.html", DASHBOARD_DIR)
    
    commit_msg = f"Auto-update metrics trend dashboard: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    run_command(f'git commit -m "{commit_msg}"', DASHBOARD_DIR)
    
    push_res = run_command("git push origin main", DASHBOARD_DIR)
    if push_res.returncode == 0:
        print("🎉 Successfully pushed to GitHub! The hosted dashboard will update shortly.")
    else:
        print("⚠️ Push failed or no changes to push. Check log output above.")

if __name__ == '__main__':
    main()
