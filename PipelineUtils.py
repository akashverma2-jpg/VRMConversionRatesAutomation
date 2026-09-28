import os
import pandas as pd
from datetime import datetime

DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')

def get_target_month_name():
    """
    Retrieves target month string from environment or falls back to current month.
    """
    target_month = os.getenv("TARGET_MONTH")
    received_date = os.getenv("RECEIVED_DATE")
    if target_month:
        return target_month.strip()
    if received_date:
        try:
            dt = datetime.strptime(received_date, '%d-%b-%Y')
            return dt.strftime('%B')
        except Exception:
            pass
    return datetime.now().strftime('%B')

def get_target_sales_file(download_folder=None):
    """
    Finds the active sales Excel file with robust fallback:
    1. CURRENT_SALES_FILE environment variable override.
    2. Matches target month (both full name 'September' and abbreviation 'Sep').
    3. Selects latest file based on internal max data date, avoiding reliance on OS system edit date.
    """
    if download_folder is None:
        download_folder = DOWNLOAD_FOLDER

    current_file = os.getenv("CURRENT_SALES_FILE")
    if current_file and os.path.exists(current_file):
        return os.path.abspath(current_file)

    # Check marker file written by SalesFileDownload.py
    marker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.current_sales_file.txt')
    if os.path.exists(marker_file):
        try:
            with open(marker_file, 'r') as mf:
                marked = mf.read().strip()
                if marked and os.path.exists(marked):
                    return os.path.abspath(marked)
        except Exception:
            pass

    if not os.path.exists(download_folder):
        return None

    files = [
        os.path.join(download_folder, f) 
        for f in os.listdir(download_folder) 
        if f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')
    ]
    if not files:
        return None

    target_month = get_target_month_name().strip().lower()
    short_month = target_month[:3] if target_month else ""

    candidates = [
        f for f in files 
        if (target_month and target_month in os.path.basename(f).lower()) or 
           (short_month and short_month in os.path.basename(f).lower())
    ]
    if not candidates:
        candidates = files

    def get_file_score(f):
        try:
            xl = pd.ExcelFile(f, engine='openpyxl')
            health_sheet = next((s for s in xl.sheet_names if 'health' in s.lower() and 'unique' not in s.lower()), None)
            if health_sheet:
                df = pd.read_excel(xl, sheet_name=health_sheet, usecols=['Date'])
                max_date = pd.to_datetime(df['Date']).max()
                if pd.notna(max_date):
                    return (max_date.timestamp(), os.path.getmtime(f))
        except Exception:
            pass
        return (0, os.path.getmtime(f))

    best_file = max(candidates, key=get_file_score)
    return os.path.abspath(best_file)
