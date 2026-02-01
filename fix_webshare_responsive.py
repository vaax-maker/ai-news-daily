#!/usr/bin/env python3
"""
Apply responsive CSS wrapper to all existing webshare HTML files.
"""
import os
import re
from pathlib import Path

WEBSHARE_DIR = Path("docs/webshare")

RESPONSIVE_CSS = '''
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
</style>'''

VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1">'

def wrap_with_responsive_css(html):
    """Add responsive CSS and viewport meta to HTML."""
    # Skip if already has responsive wrapper
    if 'Responsive Wrapper - Auto-injected' in html:
        return html, False
    
    modified = False
    
    # Add viewport meta if missing
    if not re.search(r'<meta[^>]*viewport', html, re.IGNORECASE):
        if re.search(r'<head[^>]*>', html, re.IGNORECASE):
            html = re.sub(r'(<head[^>]*>)', r'\1\n' + VIEWPORT_META, html, flags=re.IGNORECASE)
        else:
            html = VIEWPORT_META + '\n' + html
        modified = True
    
    # Add responsive CSS
    if re.search(r'</head>', html, re.IGNORECASE):
        html = re.sub(r'(</head>)', RESPONSIVE_CSS + r'\n\1', html, flags=re.IGNORECASE)
    elif re.search(r'<body[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<body[^>]*>)', RESPONSIVE_CSS + r'\n\1', html, flags=re.IGNORECASE)
    else:
        html = RESPONSIVE_CSS + '\n' + html
    modified = True
    
    return html, modified

def main():
    if not WEBSHARE_DIR.exists():
        print(f"Directory not found: {WEBSHARE_DIR}")
        return
    
    html_files = list(WEBSHARE_DIR.glob("*.html"))
    # Exclude list page
    html_files = [f for f in html_files if 'secret_list' not in f.name]
    
    print(f"Found {len(html_files)} HTML files")
    
    updated = 0
    skipped = 0
    
    for file_path in html_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            new_html, was_modified = wrap_with_responsive_css(html)
            
            if was_modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_html)
                print(f"✓ Updated: {file_path.name}")
                updated += 1
            else:
                print(f"- Skipped (already has): {file_path.name}")
                skipped += 1
                
        except Exception as e:
            print(f"✗ Error with {file_path.name}: {e}")
    
    print(f"\nDone! Updated: {updated}, Skipped: {skipped}")

if __name__ == "__main__":
    main()
