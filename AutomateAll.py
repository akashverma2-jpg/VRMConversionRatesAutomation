import os
import sys
import subprocess
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIG ---
TREND_FILE = 'MTD_ConversionRate_Trend.xlsx'

def get_last_day_of_month(any_date):
    """Calculates the last day of the month for any given date object."""
    next_month = any_date.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)

def check_month_completion():
    """Checks the Trend Tracker to see if the previous month was fully closed."""
    if not os.path.exists(TREND_FILE):
        return None, False

    try:
        df = pd.read_excel(TREND_FILE)
        if df.empty or 'Date' not in df.columns: return None, False
        
        df['Date'] = pd.to_datetime(df['Date'])
        last_recorded_date = df['Date'].max()
        last_day = get_last_day_of_month(last_recorded_date)
        
        # If last entry isn't month-end and we are now in a new month
        if last_recorded_date.date() < last_day.date() and datetime.now().date() > last_day.date():
            return last_recorded_date.strftime('%B'), True
    except Exception as e:
        print(f"⚠️ Gap Check Warning: {e}")
    
    return None, False

def run_step(script_name, target_month=None, manual_sub=None, manual_date=None):
    env = os.environ.copy()
    # Aligning names with SalesFileDownload.py expectations
    if target_month: env["TARGET_MONTH"] = target_month
    if manual_sub: env["SUBJECT_KEYWORD"] = manual_sub
    if manual_date: env["RECEIVED_DATE"] = manual_date
    
    print(f"\n⌛ Running {script_name}...")
    process = subprocess.run([sys.executable, script_name], env=env)
    
    if process.returncode != 0:
        print(f"❌ CRITICAL ERROR in {script_name}. Pipeline stopped.")
        sys.exit(1)

def main():
    print("="*40)
    print("   CONVERSION PIPELINE: MISSION CONTROL")
    print("="*40)

    scripts = ["SalesFileDownload.py", "SalesFileCleaning.py", "QueryGenerator.py", 
               "SupersetBot.py", "MergeData.py", "CollateSalesData.py", "CalculateMetrics.py", "CalculateWeeklyMetrics.py"]

    print("Available Steps:")
    for i, script in enumerate(scripts, 1):
        print(f"{i}. {script}")
        
    start_step = input(f"\nEnter step number to start from (1-{len(scripts)}) [Press Enter for 1]: ").strip()
    try:
        start_index = int(start_step) - 1 if start_step else 0
        if not (0 <= start_index < len(scripts)):
            print("⚠️ Invalid step number. Starting from step 1.")
            start_index = 0
    except ValueError:
        print("⚠️ Invalid input. Starting from step 1.")
        start_index = 0

    scripts_to_run = scripts[start_index:]
    print(f"\n🚀 Will execute from: {scripts_to_run[0]}")

    if start_index == 0:
        print("\n1. 🤖 Auto-Run (Trend Gap Check + Current)")
        print("2. 🛠️  Manual Search (Specific Subject + Date)")
        
        choice = input("\nSelect Mode (1/2): ")

        if choice == '2':
            # --- MANUAL MODE ---
            sub = input("📧 Enter Subject Keyword: ").strip()
            date_str = input("📅 Enter Date (DD-Mon-YYYY): ").strip()
            
            print(f"\n🎯 Targeted Run: {sub} from {date_str}")
            for script in scripts_to_run:
                run_step(script, manual_sub=sub, manual_date=date_str)

        else:
            # --- AUTO-RUN MODE ---
            # 1. Check for gaps in the previous month
            missing_month, is_missing = check_month_completion()
            
            if is_missing:
                print(f"\n🚨 GAP DETECTED: {missing_month} is incomplete in {TREND_FILE}.")
                catch_up = input(f"❓ Run catch-up for {missing_month}? (y/n): ")
                if catch_up.lower() == 'y':
                    for script in scripts_to_run:
                        run_step(script, target_month=missing_month)
                    print(f"\n✅ Catch-up for {missing_month} complete.")

            # 2. Run for current month
            print("\n🌟 Starting regular current month automation...")
            for script in scripts_to_run:
                run_step(script)
    else:
        # Resuming from a later step (skip the mode prompt)
        print(f"\n🌟 Resuming automation from {scripts_to_run[0]}...")
        for script in scripts_to_run:
            run_step(script)

    print("\n" + "="*40)
    print("🏁 ALL TASKS FINISHED SUCCESSFULLY.")
    print("="*40)

if __name__ == "__main__":
    main()