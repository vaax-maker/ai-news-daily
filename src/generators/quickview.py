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


def scope_injected_styles(html: str) -> str:
    """
    Scope global selectors in injected <style> blocks to .quickview-body
    to prevent them from breaking the main page layout.
    """
    import re
    
    # Global element selectors that should be scoped to .quickview-body
    GLOBAL_TAGS = [
        'body', 'html', 'main',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'a', 'span', 'em', 'strong', 'b', 'i', 'u',
        'ul', 'ol', 'li',
        'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
        'blockquote', 'pre', 'code',
        'img', 'figure', 'figcaption',
        'section', 'article', 'nav', 'header', 'footer', 'aside',
        'div', 'hr', 'br',
    ]
    
    def replace_selectors(match):
        style_content = match.group(1)
        
        # Replace standalone tag selectors: "tag {" → ".quickview-body tag {"
        # But skip when already scoped (e.g., ".quickview-body p {")
        # and skip selectors that are part of class/id (e.g., ".tag-name {")
        for tag in GLOBAL_TAGS:
            if tag in ('body', 'html'):
                # body/html → replace with .quickview-body itself
                style_content = re.sub(
                    r'(?<![.\-#\w])' + tag + r'\s*\{',
                    '.quickview-body {',
                    style_content, flags=re.IGNORECASE
                )
            else:
                # Other tags → prepend .quickview-body
                style_content = re.sub(
                    r'(?<![.\-#\w])' + tag + r'\s*([,\{])',
                    r'.quickview-body ' + tag + r' \1',
                    style_content, flags=re.IGNORECASE
                )
        
        # Also scope :root { to .quickview-body {
        style_content = re.sub(
            r':root\s*\{',
            '.quickview-body {',
            style_content, flags=re.IGNORECASE
        )
        
        return f'<style>{style_content}</style>'

    # Apply to all style blocks
    return re.sub(r'<style>(.*?)</style>', replace_selectors, html, flags=re.DOTALL | re.IGNORECASE)

def wrap_with_responsive_css(html: str) -> str:
    """
    Wrap HTML content with scoped responsive CSS for mobile optimization.
    This injects styles that target .quickview-body children to ensure
    responsiveness of tables, images, and pre blocks.
    """
    # First, scope any existing styles in the HTML
    html = scope_injected_styles(html)

    # Scoped CSS - targets .quickview-body specifically to avoid global pollution
    responsive_css = """
<style>
/* Responsive Wrapper - Scoped */
.quickview-body {
    word-break: keep-all;
    overflow-wrap: break-word;
}
.quickview-body img, 
.quickview-body video, 
.quickview-body iframe { 
    max-width: 100%; 
    height: auto; 
}
.quickview-body table { 
    width: 100%; 
    display: block; 
    overflow-x: auto; 
}
.quickview-body pre, 
.quickview-body code { 
    overflow-x: auto; 
    white-space: pre-wrap; 
    word-wrap: break-word; 
}
@media (max-width: 768px) {
    .quickview-body { 
        font-size: 15px; 
    }
    .quickview-body h1 { font-size: 1.5rem; }
    .quickview-body h2 { font-size: 1.25rem; }
    .quickview-body h3 { font-size: 1.1rem; }
}
</style>"""
    
    # Avoid adding if already present (simple check)
    if "/* Responsive Wrapper - Scoped */" in html:
        return html
        
    return responsive_css + '\n' + html

def inject_minimal_responsive_css(html: str) -> str:
    """
    Injects only essential, non-destructive mobile CSS into a full HTML document
    without overriding global layouts or sizes.
    """
    responsive_css = """
<style>
/* Minimal Mobile CSS (Safe for Full Pages) */
img, video, iframe { 
    max-width: 100%; 
    height: auto; 
}
table, pre { 
    max-width: 100%; 
    overflow-x: auto; 
}
</style>
"""
    viewport_meta = '<meta name="viewport" content="width=device-width, initial-scale=1">'

    # 1. Inject Viewport if missing
    import re
    if not re.search(r'<meta[^>]*viewport', html, re.IGNORECASE):
        if re.search(r'<head[^>]*>', html, re.IGNORECASE):
            html = re.sub(r'(<head[^>]*>)', r'\1\n' + viewport_meta, html, count=1, flags=re.IGNORECASE)
        else:
            html = viewport_meta + '\n' + html

    # 2. Inject Minimal CSS
    if "/* Minimal Mobile CSS" not in html:
        if re.search(r'</head>', html, re.IGNORECASE):
            html = re.sub(r'(</head>)', responsive_css + '\n' + r'\1', html, count=1, flags=re.IGNORECASE)
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
        
        # Generate individual page HTML
        page_url = f"https://vaax-maker.github.io/ai-news-daily/quickview/{page_id}.html"
        
        is_full_page = '<!doctype' in html_content.lower() or '<html' in html_content.lower() or '<body' in html_content.lower()
        
        if is_full_page:
            # For full pages, we preserve original code exactly, but add minimal responsive handles
            print(f"[Quickview] {page_id} is a full HTML document. Preserving raw structure.")
            cleaned_html = inject_minimal_responsive_css(cleaned_html)
            page_html = cleaned_html
            
            # Optionally inject a small navigation back button if needed (commented out for now to ensure 1:1 match)
            # return_btn = f'<div style="position:fixed; bottom:20px; right:20px; z-index:9999;"><a href="../quickview/index.html" style="background:#047857;color:#fff;padding:10px 15px;text-decoration:none;border-radius:20px;font-family:sans-serif;font-size:14px;box-shadow:0 2px 5px rgba(0,0,0,0.2);">← 퀵뷰 목록</a></div>'
            # if '</body>' in page_html:
            #     page_html = page_html.replace('</body>', return_btn + '</body>')
            # else:
            #     page_html += return_btn
                
        else:
            # Apply Responsive Wrapper (Mobile Optimization) and layout for snippets
            cleaned_html = wrap_with_responsive_css(cleaned_html)
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
