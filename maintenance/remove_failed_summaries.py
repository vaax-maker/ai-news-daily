
import os
from bs4 import BeautifulSoup
import glob

def clean_failed_summaries(category):
    targets = glob.glob(f"docs/{category}/daily/*.html")
    print(f"Checking {len(targets)} files in {category}...")
    
    total_removed = 0
    
    for filepath in targets:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "요약 실패" not in content:
            continue
            
        soup = BeautifulSoup(content, 'html.parser')
        modified = False
        
        # Find elements containing "요약 실패"
        # Case 1: Plain text in p or div
        # Case 2: Inside summary box
        
        # Strategy: Find all text nodes, check parent
        # We look for the main card container to remove
        
        # Common containers for news items in this project
        # 1. article.news-card (Tile view)
        # 2. li.news-item (List view)
        
        items_to_remove = []
        
        # Check all potential containers
        containers = soup.select('article.news-card, li.news-item, .news-tile')
        
        for item in containers:
            if "요약 실패" in item.get_text():
                items_to_remove.append(item)
        
        if items_to_remove:
            for item in items_to_remove:
                item.decompose() # Remove from DOM
                total_removed += 1
            modified = True
            
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            print(f"  Fixed: {os.path.basename(filepath)} (Removed {len(items_to_remove)} items)")

    print(f"Total {total_removed} failed items removed from {category}.\n")

if __name__ == "__main__":
    clean_failed_summaries("ai")
    clean_failed_summaries("xr")
