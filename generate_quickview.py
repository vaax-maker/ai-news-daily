"""
Quickview Page Generator Script

This script reads pending quickview pages from Firestore and generates
static HTML files in docs/quickview/ for GitHub Pages deployment.

Run this script after quickview pages are created via the admin panel.
"""

import os
import datetime

# Only import firebase_admin if needed
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("[Quickview] firebase_admin not installed. Skipping Firestore sync.")

from src.generators.html import render_quickview_index, render_quickview_page


def get_firestore_client():
    """Initialize and return Firestore client."""
    if not FIREBASE_AVAILABLE:
        return None
    
    if not firebase_admin._apps:
        cred_path = os.path.join(os.path.dirname(__file__), 'vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json')
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            print(f"[Quickview] Firebase credentials not found at {cred_path}")
            return None
    
    return firestore.client()


def process_quickview_pages():
    """
    Fetch quickview pages from Firestore and generate static HTML files.
    """
    db = get_firestore_client()
    if not db:
        print("[Quickview] Firestore not available. Skipping.")
        return []
    
    # Create quickview directory
    quickview_dir = "docs/quickview"
    os.makedirs(quickview_dir, exist_ok=True)
    
    # Fetch all quickview pages from Firestore
    docs = db.collection("quickview_pages").order_by("createdAt", direction=firestore.Query.DESCENDING).stream()
    
    pages = []
    now_timestamp = datetime.datetime.now().timestamp()
    new_threshold = 24 * 60 * 60  # 24 hours for NEW badge
    
    for doc in docs:
        data = doc.to_dict()
        page_id = data.get("id")
        title = data.get("title", "Untitled")
        html_content = data.get("html", "")
        created_at = data.get("createdAt")
        
        if not page_id or not html_content:
            continue
        
        # Format display date
        if created_at:
            dt = created_at
            created_display = dt.strftime("%Y년 %m월 %d일 %H:%M")
            created_ts = dt.timestamp()
        else:
            created_display = "날짜 없음"
            created_ts = 0
        
        # Generate individual page HTML
        page_url = f"https://vaax-maker.github.io/ai-news-daily/quickview/{page_id}.html"
        page_html = render_quickview_page(title, html_content, created_display, page_url)
        page_path = os.path.join(quickview_dir, f"{page_id}.html")
        
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        
        # Collect page info for index
        is_new = created_ts > 0 and (now_timestamp - created_ts) < new_threshold
        pages.append({
            "id": page_id,
            "title": title,
            "created_at": created_ts,
            "created_display": created_display,
            "is_new": is_new,
            "url": f"quickview/{page_id}.html"
        })
        
        print(f"[Quickview] Generated: {page_id}.html")
    
    # Generate index page
    if pages:
        index_html = render_quickview_index(pages)
        with open(os.path.join(quickview_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)
        print(f"[Quickview] Generated index.html with {len(pages)} pages")
    else:
        # Generate empty index
        index_html = render_quickview_index([])
        with open(os.path.join(quickview_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)
        print("[Quickview] Generated empty index.html")
    
    return pages


def get_latest_quickviews(limit=5):
    """
    Return the latest N quickview pages for dashboard display.
    """
    db = get_firestore_client()
    if not db:
        return []
    
    docs = db.collection("quickview_pages").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(limit).stream()
    
    pages = []
    now_timestamp = datetime.datetime.now().timestamp()
    new_threshold = 24 * 60 * 60
    
    for doc in docs:
        data = doc.to_dict()
        page_id = data.get("id")
        created_at = data.get("createdAt")
        
        if created_at:
            created_ts = created_at.timestamp()
            created_display = created_at.strftime("%Y년 %m월 %d일")
        else:
            created_ts = 0
            created_display = ""
        
        is_new = created_ts > 0 and (now_timestamp - created_ts) < new_threshold
        
        pages.append({
            "id": page_id,
            "title": data.get("title", ""),
            "summary": data.get("summary", ""),
            "created_display": created_display,
            "is_new": is_new,
            "url": f"quickview/{page_id}.html"
        })
    
    return pages


if __name__ == "__main__":
    process_quickview_pages()
