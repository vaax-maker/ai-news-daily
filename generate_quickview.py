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

from dotenv import load_dotenv
load_dotenv()

from src.generators.html import render_quickview_index, render_quickview_page


def transform_timestamp_links(html_content: str) -> str:
    """
    Transform YouTube timestamp links to in-page playback.
    
    Converts external YouTube URLs with timestamps (youtu.be/xxx?t=123 or youtube.com/watch?v=xxx&t=123s)
    to data-time attributes with JavaScript-based in-page iframe control.
    """
    import re
    
    # Check if content has YouTube iframe
    iframe_match = re.search(r'<iframe[^>]*src=["\']([^"\']*youtube\.com/embed/([a-zA-Z0-9_-]+)[^"\']*)["\']', html_content)
    if not iframe_match:
        return html_content
    
    video_id = iframe_match.group(2)
    
    # Check if there are timestamp links
    timestamp_pattern = r'href=["\']https?://(youtu\.be/[a-zA-Z0-9_-]+\?t=|www\.youtube\.com/watch\?[^"\']*t=|youtube\.com/watch\?[^"\']*t=)(\d+)s?["\']'
    if not re.search(timestamp_pattern, html_content):
        return html_content
    
    # 1. Add id and enablejsapi to iframe (if not already present)
    if 'id="youtube-player"' not in html_content:
        html_content = re.sub(
            r'<iframe([^>]*src=["\'][^"\']*youtube\.com/embed/)',
            r'<iframe id="youtube-player"\1',
            html_content
        )
    
    # Add enablejsapi=1 to iframe src if not present
    if 'enablejsapi=1' not in html_content:
        # For iframes without query params
        html_content = re.sub(
            r'(youtube\.com/embed/[a-zA-Z0-9_-]+)(["\'])',
            r'\1?enablejsapi=1\2',
            html_content
        )
    
    # 2. Convert timestamp links to data-time attributes
    # Pattern captures the full href including any existing class attribute
    def convert_link(match):
        seconds = match.group(2)
        return f'href="#" data-time="{seconds}"'
    
    html_content = re.sub(timestamp_pattern, convert_link, html_content)


    
    # 3. Add JavaScript for timestamp handling (before </body> or at end)
    timestamp_script = f'''
<!-- YouTube Timestamp In-Page Playback Script -->
<script>
document.addEventListener('DOMContentLoaded', function() {{
    const iframe = document.getElementById('youtube-player') || document.querySelector('iframe[src*="youtube.com/embed"]');
    const videoId = '{video_id}';
    
    document.querySelectorAll('.timestamp-link, a[data-time]').forEach(function(link) {{
        link.addEventListener('click', function(e) {{
            e.preventDefault();
            const seconds = parseInt(this.getAttribute('data-time'), 10);
            
            if (iframe) {{
                iframe.src = 'https://www.youtube.com/embed/' + videoId + '?start=' + seconds + '&autoplay=1&enablejsapi=1';
                iframe.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }});
    }});
}});
</script>
'''
    
    # Insert before </body> if exists, otherwise append
    if '</body>' in html_content:
        html_content = html_content.replace('</body>', timestamp_script + '</body>')
    else:
        html_content += timestamp_script
    
    return html_content


def wrap_with_responsive_css(html: str) -> str:
    """Wrap HTML content with responsive CSS for mobile optimization."""
    responsive_css = """
<style>
/* Responsive Wrapper - Auto-injected */
html { font-size: 16px; }
body { 
    max-width: 900px; 
    margin: 0 auto; 
    padding: 1rem; 
    line-height: 1.7;
    word-break: keep-all;
}
img, video, iframe { 
    max-width: 100%; 
    height: auto; 
}
table { 
    width: 100%; 
    display: block; 
    overflow-x: auto; 
}
pre, code { 
    overflow-x: auto; 
    white-space: pre-wrap; 
    word-wrap: break-word;
}
@media (max-width: 768px) {
    body { 
        padding: 0.75rem; 
        font-size: 15px; 
    }
    h1 { font-size: 1.5rem; }
    h2 { font-size: 1.25rem; }
    h3 { font-size: 1.1rem; }
}
</style>"""
    
    import re
    # Check if viewport meta exists
    if not re.search(r'<meta[^>]*viewport', html, re.IGNORECASE):
        viewport_meta = '<meta name="viewport" content="width=device-width, initial-scale=1">'
        if re.search(r'<head[^>]*>', html, re.IGNORECASE):
            html = re.sub(r'(<head[^>]*>)', r'\1\n' + viewport_meta, html, count=1, flags=re.IGNORECASE)
        else:
            html = viewport_meta + '\n' + html

    # Insert responsive CSS before </head> or at start
    if re.search(r'</head>', html, re.IGNORECASE):
        html = re.sub(r'</head>', responsive_css + '\n</head>', html, count=1, flags=re.IGNORECASE)
    elif re.search(r'<body[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<body[^>]*>)', responsive_css + '\n' + r'\1', html, count=1, flags=re.IGNORECASE)
    else:
        html = responsive_css + '\n' + html
        
    return html


def get_firestore_client():
    """Initialize and return Firestore client."""
    if not FIREBASE_AVAILABLE:
        return None
    
    if not firebase_admin._apps:
        # Try environment variable first (for GitHub Actions)
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if sa_json:
            import tempfile
            import json
            try:
                # sa_json is a JSON string from GitHub Secrets
                if sa_json.startswith('{'):
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as f:
                        f.write(sa_json)
                        temp_path = f.name
                    cred = credentials.Certificate(temp_path)
                    firebase_admin.initialize_app(cred)
                    print("[Quickview] Firebase initialized from environment variable")
                else:
                    cred = credentials.Certificate(sa_json)
                    firebase_admin.initialize_app(cred)
            except Exception as e:
                print(f"[Quickview] Failed to init Firebase from env: {e}")
                return None
        else:
            # Fall back to local file
            cred_path = os.path.join(os.path.dirname(__file__), 'vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print("[Quickview] Firebase initialized from local file")
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
        
        # Format display date (convert UTC to KST)
        if created_at:
            # Firestore timestamp is in UTC, convert to KST (+9 hours)
            kst_offset = datetime.timedelta(hours=9)
            dt_kst = created_at + kst_offset
            created_display = dt_kst.strftime("%Y년 %m월 %d일 %H:%M")
            created_ts = created_at.timestamp()
        else:
            created_display = "날짜 없음"
            created_ts = 0
        
        # Remove duplicate title from HTML content
        # If the first h1 or h2 matches the title, remove it
        import re
        cleaned_html = html_content
        heading_match = re.match(r'^(\s*<h[12][^>]*>)(.*?)(</h[12]>)', html_content, re.IGNORECASE | re.DOTALL)
        if heading_match:
            heading_text = re.sub(r'<[^>]+>', '', heading_match.group(2)).strip()
            if heading_text == title.strip():
                # Remove the duplicate heading
                cleaned_html = html_content[heading_match.end():].strip()
        
        # Sanitize malformed Markdown links in HTML attributes
        # Pattern: src="[url](url)" or href="[url](url)"
        # Regex to catch [url](url) where text is same as url (common Notion/Obsidian export issue)
        # Also handles [url](url) generally if it's inside quotes
        import re
        # Fix 1: attribute="[url](url)" -> attribute="url"
        cleaned_html = re.sub(r'="\[([^\]]+)\]\(([^)]+)\)"', r'="\2"', cleaned_html)
        # Fix 2: attribute='[url](url)' -> attribute='url'
        cleaned_html = re.sub(r"='\[([^\]]+)\]\(([^)]+)\)'", r"='\2'", cleaned_html)
        # Fix 3: tag.src = "[url](url)" (JS)
        cleaned_html = re.sub(r'= "\[([^\]]+)\]\(([^)]+)\)"', r'= "\2"', cleaned_html)
        
        # Fix 4: Handle HTML entities (&quot;)
        cleaned_html = re.sub(r'=&quot;\[([^\]]+)\]\(([^)]+)\)&quot;', r'=&quot;\2&quot;', cleaned_html)
        
        # Transform YouTube timestamp links for in-page playback
        cleaned_html = transform_timestamp_links(cleaned_html)
        
        # Apply Responsive Wrapper (Mobile Optimization)
        cleaned_html = wrap_with_responsive_css(cleaned_html)
        
        # Generate individual page HTML
        page_url = f"https://vaax-maker.github.io/ai-news-daily/quickview/{page_id}.html"
        page_html = render_quickview_page(title, cleaned_html, created_display, page_url, created_at=created_ts)
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
            # Convert UTC to KST (+9 hours)
            kst_offset = datetime.timedelta(hours=9)
            dt_kst = created_at + kst_offset
            created_display = dt_kst.strftime("%Y년 %m월 %d일")
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
