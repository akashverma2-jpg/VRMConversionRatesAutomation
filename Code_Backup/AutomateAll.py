import subprocess
import sys
import time

# The exact order of your workflow
PIPELINE = [
    "SalesFileDownload.py",
    "SalesFileCleaning.py",
    "QueryGenerator.py",
    "SupersetBot.py",
    "MergeData.py",
    "CalculateMetrics.py"
]

def run_workflow():
    start_time = time.time()
    print("🚀 Starting the Conversion Rate Automation Pipeline...")
    print("=" * 50)

    for script in PIPELINE:
        print(f"⌛ Running: {script}...")
        
        # Runs the script and waits for it to finish
        result = subprocess.run([sys.executable, script])

        if result.returncode == 0:
            print(f"✅ {script} finished successfully.\n")
        else:
            print(f"❌ CRITICAL ERROR: {script} failed.")
            print("🛑 Stopping pipeline to prevent data mismatch.")
            sys.exit(1)

    end_time = time.time()
    elapsed = round((end_time - start_time) / 60, 2)
    print("=" * 50)
    print(f"🎉 SUCCESS: All 6 scripts completed in {elapsed} minutes.")
    print(f"📁 Check your folder for the latest Daily Breakdown and Trend Tracker.")

if __name__ == "__main__":
    run_workflow()