#!/usr/bin/env python3
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
import datetime
import requests
from bs4 import BeautifulSoup
import re

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generators.html import render_daily_page
from src.generators.llm import summarize_article
from src.config import load_categories
from src.utils.common import markdown_bold_to_highlight, extract_source_name, sanitize_summary, trim_summary_lines
from rebuild_all_html import rebuild_archives

def scrape_article_content(url):
    """Scrape title, text, and image from a URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Extract title (fallback if needed)
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"] if og_title else soup.title.string if soup.title else ""
        
        # Extract image
        og_image = soup.find("meta", property="og:image")
        image_url = og_image["content"] if og_image else ""
        
        # Extract text (simple heuristic)
        # Remove scripts and styles
        for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            script.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        # Basic cleanup: take first 3000 chars roughly
        text = text[:4000]
        
        return {
            "title": title,
            "text": text,
            "image": image_url
        }
    except Exception as e:
        print(f"Scraping failed for {url}: {e}")
        return None

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
        
        url = data.get('url')
        current_title = data.get('title')
        current_summary = data.get('summary')
        current_image = data.get('image')
        
        scraped_data = None
        
        # If components are missing, try to scrape
        if url and (not current_summary or not current_image):
            print(f"Scraping content for: {url}")
            scraped_data = scrape_article_content(url)
        
        # Title fallback
        final_title = current_title
        if not final_title and scraped_data:
            final_title = scraped_data['title']
            
        # Image fallback
        final_image = current_image
        if not final_image and scraped_data:
            final_image = scraped_data['image']
            
        # Summary generation
        final_summary = current_summary
        if not final_summary and scraped_data and scraped_data['text']:
            print("Generating summary via LLM...")
            try:
                final_summary = summarize_article(
                    text=scraped_data['text'],
                    title=final_title or "Untitled",
                    display_name="Manual Entry"
                )
            except Exception as e:
                print(f"LLM Summary generation failed: {e}")
                final_summary = "요약을 생성할 수 없습니다."
        
        if final_summary:
            final_summary = sanitize_summary(final_summary)
            # trim_summary_lines is intended for single-paragraph summaries usually,
            # but if LLM output is structured (headings etc), trim might break it 
            # or it might be fine. sanitize_summary removes <think>.
            # Let's trust sanitize_summary is enough for <think> removal.
            # We can optionally use trim if we want strictly 3-5 lines, but
            # summarize_article returns formatted text with bullets. 
            # If we trim it naively, we might lose structure.
            # Let's just use sanitize_summary first.


        # Prepare article data for template
        # Must match keys used in daily_list.html
        article = {
            "title": final_title,
            "link": url,
            "summary": final_summary,
            "summary_html": markdown_bold_to_highlight(final_summary) if final_summary else "",
            "source": data.get('source'),
            "source_name": data.get('source') or "Direct Link",
            "published": data.get('published'), # "YYYY-MM-DD HH:MM"
            "published_display": data.get('published') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "image_url": final_image,
            "is_new": True 
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
            'title': final_title,         # Update DB with populated values
            'summary': final_summary,
            'image': final_image,
            'archivePath': output_path,
            'processedAt': firestore.SERVER_TIMESTAMP
        })
        processed_count += 1

    if processed_count > 0:
        print("--- Rebuilding Indexes ---")
        # Update Archive Indexes
        rebuild_archives()
        # Note: Ideally running full rebuild_dashboard is good too, but verifying based on user request "Archive Loading"
        # The archive index update should facilitate valid display.

    print("--- [Manual Archive Processing] Complete ---")

if __name__ == "__main__":
    process_manual_articles()
