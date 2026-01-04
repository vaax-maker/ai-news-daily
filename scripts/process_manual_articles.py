#!/usr/bin/env python3
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generators.html import render_daily_page
from src.config import load_categories
from rebuild_all_html import rebuild_archives, rebuild_dashboard

def process_manual_articles():
    print("--- [Manual Archive Processing] Started ---")
    
    # Initialize Firebase
    cred_path = "/Users/fovea/Documents/vsc-codex/VAAXfinal/vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json"
    if not os.path.exists(cred_path):
        print(f"Error: Firebase credential not found at {cred_path}")
        return

    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    
    # Query pending articles
    docs = db.collection('manual_articles').where(field_path='status', op_string='==', value='pending').get()
    
    if not docs:
        print("No pending articles found.")
        return

    print(f"Found {len(docs)} pending articles.")
    categories = load_categories()
    
    processed_count = 0
    
    for doc in docs:
        data = doc.to_dict()
        category = data.get('category', 'ai').lower()
        if category not in categories:
            print(f"Skipping unknown category: {category}")
            continue
            
        config = categories[category]
        
        # Prepare article data for template
        article = {
            "title": data.get('title'),
            "link": data.get('url'),
            "summary": data.get('summary'),
            "source": data.get('source'),
            "published": data.get('published'), # "YYYY-MM-DD HH:MM"
            "image": "" # No image for manual summary currently
        }
        
        date_str = data.get('dateStr') # "YYYY-MM-DD"
        time_str = data.get('timeStr') # "HHMMSSmm" or similar
        
        if not date_str or not time_str:
            # Fallback if missing
            now = datetime.datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H%M%S")

        # Generate HTML
        html_content = render_daily_page(
            articles=[article],
            date_str=date_str,
            time_str=f"{time_str[:2]}:{time_str[2:4]}",
            config=config,
            active_tab=config.key
        )
        
        # Save file
        filename = f"{date_str}_{time_str}.html"
        output_dir = f"docs/{category}/daily"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print(f"Generated: {output_path}")
        
        # Update Firebase status
        doc.reference.update({
            'status': 'success',
            'archivePath': output_path,
            'processedAt': firestore.SERVER_TIMESTAMP
        })
        processed_count += 1

    if processed_count > 0:
        print("--- Rebuilding Indexes ---")
        # Update Archive Indexes
        a_previews, links = rebuild_archives()
        
        # Note: We are NOT fully rebuilding dashboard here (rebuild_dashboard arg list is complex).
        # But rebuild_archives() updates the category index pages (docs/ai/index.html) which is what user checks.
        # Ideally we should run rebuild_dashboard too, but let's stick to archives for now or mock args.
        # Actually rebuild_all_html.py main block does everything.
        # For now, let's trust rebuild_archives() to update the specific category page.
        
    print("--- [Manual Archive Processing] Complete ---")

if __name__ == "__main__":
    process_manual_articles()
