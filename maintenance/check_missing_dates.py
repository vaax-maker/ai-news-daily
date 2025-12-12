
import os
from datetime import datetime, timedelta

DOCS_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs'
AI_DAILY = os.path.join(DOCS_DIR, 'ai/daily')
XR_DAILY = os.path.join(DOCS_DIR, 'xr/daily')

START_DATE = datetime(2025, 6, 10)
END_DATE = datetime(2025, 12, 11)

def get_existing_dates(directory):
    dates = set()
    if not os.path.exists(directory): return dates
    for filename in os.listdir(directory):
        # Format: YYYY-MM-DD_....html
        if len(filename) >= 10:
            try:
                date_str = filename[:10]
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                dates.add(dt)
            except:
                pass
    return dates

def main():
    ai_dates = get_existing_dates(AI_DAILY)
    xr_dates = get_existing_dates(XR_DAILY)
    all_dates = ai_dates.union(xr_dates)
    
    current = START_DATE
    missing_count = 0
    print(f"Checking missing dates from {START_DATE.date()} to {END_DATE.date()}...")
    
    while current <= END_DATE:
        if current not in all_dates:
            # Check if it's a weekend (optional, but daily news usually skips weekends?)
            # User didn't specify, so list all.
            day_name = current.strftime('%A')
            print(f"Missing: {current.date()} ({day_name})")
            missing_count += 1
        current += timedelta(days=1)
        
    if missing_count == 0:
        print("No missing dates found!")
    else:
        print(f"Total missing days: {missing_count}")

if __name__ == '__main__':
    main()
