import pandas as pd
import os
from datetime import datetime

# --- CONFIG ---
DOWNLOAD_FOLDER = './downloads'
MASTER_FILE = 'Collated_Sales_Master.xlsx'
OUTPUT_FILE = 'Weekly_Daily_Conversion_Rates.xlsx'

def get_monthly_fav_pool(month_str):
    """
    Finds the Favourite DP count for a given month (YYYY-MM).
    Since it's fixed for the month, any file for that month will have the same total.
    """
    fav_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(f'Fav_DP_Count_{month_str}')]
    if not fav_files:
        return 0
    df = pd.read_csv(os.path.join(DOWNLOAD_FOLDER, fav_files[0]))
    return df['dp_count'].sum()

def calculate_weekly_daily_metrics():
    if not os.path.exists(MASTER_FILE):
        print(f"❌ Master file {MASTER_FILE} not found.")
        return

    print(f"📂 Loading Master Data: {MASTER_FILE}")
    df_master = pd.read_excel(MASTER_FILE, engine='openpyxl')
    df_master['Date'] = pd.to_datetime(df_master['Date'])
    
    # Get all unique dates from master data and CSV downloads
    sales_dates = set(df_master['Date'].dt.strftime('%Y-%m-%d').unique())
    
    # We need supply CSVs to calculate anything
    supply_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith('InactiveSupply_') and f.endswith('.csv')]
    supply_dates = sorted([f.replace('InactiveSupply_', '').replace('.csv', '') for f in supply_files])
    
    if not supply_dates:
        print("❌ No supply files found in downloads.")
        return

    # To calculate incremental supply, we need to know the MTD count for each date
    mtd_supply_map = {}
    for d_str in supply_dates:
        df_sup = pd.read_csv(os.path.join(DOWNLOAD_FOLDER, f"InactiveSupply_{d_str}.csv"))
        mtd_supply_map[d_str] = df_sup['sum_inactive_dps_creating_quotes'].sum()

    daily_results = []
    
    # Process dates sequentially to calculate deltas
    print(f"📊 Calculating incremental metrics for {len(supply_dates)} recorded dates...")
    
    for i in range(len(supply_dates)):
        curr_date_str = supply_dates[i]
        curr_date_ts = pd.to_datetime(curr_date_str)
        month_str = curr_date_str[:7]
        
        # 1. Activation Denominator (Incremental Supply)
        mtd_curr = mtd_supply_map[curr_date_str]
        
        # Determine the start of the increment period
        if i == 0 or supply_dates[i-1][:7] != month_str:
            # First file of the month or first file ever
            mtd_prev = 0
            period_start = curr_date_ts.replace(day=1)
        else:
            mtd_prev = mtd_supply_map[supply_dates[i-1]]
            period_start = pd.to_datetime(supply_dates[i-1]) + pd.Timedelta(days=1)
        
        incremental_act_supply = mtd_curr - mtd_prev
        
        # 2. Activation Numerator (Unique Inactive DPs who sold in this period)
        period_sales = df_master[(df_master['Date'] >= period_start) & (df_master['Date'] <= curr_date_ts)]
        act_num = period_sales[period_sales['DP Status'].str.strip() == 'Inactive']['DP ID'].nunique()
        
        # 3. Favourite Metrics
        fav_den = get_monthly_fav_pool(month_str)
        # For daily/period favourite rate, we usually care about sales on that specific day vs the pool
        # But if the supply is for a period (due to gaps), we take unique sales for that period
        fav_num = period_sales[period_sales['DP Status'].str.strip().isin(['Activated by LGLC', 'Already Active'])]['DP ID'].nunique()
        
        # 4. Consolidated
        con_num = period_sales['DP ID'].nunique()
        con_den = incremental_act_supply + fav_den # Fixed Fav pool + Incremental Act supply
        
        daily_results.append({
            'Date': curr_date_ts,
            'Period_Start': period_start,
            'Act Numerator': act_num,
            'Act Denominator': incremental_act_supply,
            'Activation Rate': act_num / incremental_act_supply if incremental_act_supply > 0 else 0,
            'Fav Numerator': fav_num,
            'Fav Denominator': fav_den,
            'Favourite Conv Rate': fav_num / fav_den if fav_den > 0 else 0,
            'Consolidated Numerator': con_num,
            'Consolidated Denominator': con_den,
            'Consolidated Rate': con_num / con_den if con_den > 0 else 0
        })

    df_daily = pd.DataFrame(daily_results)
    
    # --- WEEKLY AGGREGATION ---
    # We aggregate sales by week, and calculate weekly supply delta
    df_master['Week_Start'] = df_master['Date'] - pd.to_timedelta(df_master['Date'].dt.dayofweek, unit='D')
    weekly_groups = df_master.groupby('Week_Start')
    
    weekly_results = []
    
    for week_start, week_data in weekly_groups:
        week_end = week_start + pd.Timedelta(days=6)
        month_str = week_start.strftime('%Y-%m')
        
        # 1. Numerators (Unique DPs in the week)
        act_num = week_data[week_data['DP Status'].str.strip() == 'Inactive']['DP ID'].nunique()
        fav_num = week_data[week_data['DP Status'].str.strip().isin(['Activated by LGLC', 'Already Active'])]['DP ID'].nunique()
        con_num = week_data['DP ID'].nunique()
        
        # 2. Denominators
        # Favourite is fixed for the month
        fav_den = get_monthly_fav_pool(month_str)
        
        # Activation Supply is delta over the week
        # Find MTD count at end of week and start of week
        def get_nearest_mtd(target_date):
            # Find the latest available MTD count on or before target_date
            available = [d for d in mtd_supply_map.keys() if d <= target_date.strftime('%Y-%m-%d') and d.startswith(target_date.strftime('%Y-%m'))]
            if not available: return 0
            return mtd_supply_map[max(available)]

        mtd_at_week_end = get_nearest_mtd(week_end)
        mtd_at_week_start_minus_1 = get_nearest_mtd(week_start - pd.Timedelta(days=1))
        
        weekly_act_supply = mtd_at_week_end - mtd_at_week_start_minus_1
        
        if weekly_act_supply == 0 and act_num == 0:
            continue # Skip weeks with no data
            
        weekly_results.append({
            'Week_Start': week_start,
            'Act Numerator': act_num,
            'Act Denominator': weekly_act_supply,
            'Activation Rate': act_num / weekly_act_supply if weekly_act_supply > 0 else 0,
            'Fav Numerator': fav_num,
            'Fav Denominator': fav_den,
            'Favourite Conv Rate': fav_num / fav_den if fav_den > 0 else 0,
            'Consolidated Numerator': con_num,
            'Consolidated Denominator': weekly_act_supply + fav_den,
            'Consolidated Rate': con_num / (weekly_act_supply + fav_den) if (weekly_act_supply + fav_den) > 0 else 0
        })

    df_weekly = pd.DataFrame(weekly_results)
    
    # Sort and Save
    df_daily = df_daily.sort_values(by='Date', ascending=False)
    df_weekly = df_weekly.sort_values(by='Week_Start', ascending=False)
    
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        df_daily.to_excel(writer, sheet_name='Daily_Rates', index=False)
        df_weekly.to_excel(writer, sheet_name='Weekly_Rates', index=False)
        
    print(f"✅ Success! Revised Weekly and Daily rates saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    calculate_weekly_daily_metrics()
