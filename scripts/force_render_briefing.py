import sys
import os
import datetime
import time

# Add root dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generators.html import render_mobile_landing

def main():
    now = datetime.datetime.now()
    # Mock items with timestamps
    # 1. New item (1 hour ago)
    # 2. Old item (25 hours ago)
    
    mock_ai = [
        {
            "title": "[NEW] AI breakthrough in reasoning (Mock)",
            "link": "https://example.com/1",
            "source_name": "TechCrunch",
            "timestamp": now.timestamp() - 3600 # 1 hour ago
        },
        {
            "title": "Old AI news from yesterday",
            "link": "https://example.com/2",
            "source_name": "The Verge",
            "timestamp": now.timestamp() - 90000 # 25 hours ago
        }
    ]
    
    mock_xr = [
         {
            "title": "[NEW] Apple Vision Pro 2 Rumors",
            "link": "https://example.com/3",
            "source_name": "UploadVR",
            "timestamp": now.timestamp() - 7200 # 2 hours ago
        }
    ]
    
    mock_gov = [
         {
            "title": "New Government AI Project",
            "link": "https://example.com/4",
            "dept": "Ministry of Science",
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": now.timestamp() - 1000 # very recent
        }
    ]
    
    links = {
        "ai": "ai/index.html",
        "xr": "xr/index.html",
        "gov": "gov/index.html"
    }

    print("Generating docs/briefing.html with mock data...")
    html = render_mobile_landing(mock_ai, mock_xr, mock_gov, links)
    
    with open("docs/briefing.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("Done. Check docs/briefing.html")

if __name__ == "__main__":
    main()
