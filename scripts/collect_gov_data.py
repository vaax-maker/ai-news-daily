import sys
import os

# Adjust path to find src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fetchers.gov import fetch_gov_announcements
from src.utils.storage import GovStorage

def main():
    print("Fetching government announcements...")
    items = fetch_gov_announcements(limit=50)
    print(f"Fetched {len(items)} items.")
    
    storage = GovStorage()
    saved = storage.save_announcements(items)
    print(f"Saved {len(saved)} items to {storage.data_path}")

if __name__ == "__main__":
    main()
