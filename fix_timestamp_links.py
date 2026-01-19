#!/usr/bin/env python3
"""
Fix YouTube timestamp links in quickview pages.
Converts external youtu.be links to JavaScript that controls the embedded iframe.
"""

import os
import re
from pathlib import Path
from bs4 import BeautifulSoup

QUICKVIEW_DIR = Path(__file__).parent / "docs" / "quickview"

def extract_video_id_from_iframe(soup) -> str | None:
    """Extract video ID from the embedded iframe."""
    iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
    if iframe:
        match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', iframe.get('src', ''))
        if match:
            return match.group(1)
    return None

def has_timestamp_links(content: str) -> bool:
    """Check if content has YouTube timestamp links."""
    return bool(re.search(r'href=["\']https?://(youtu\.be|youtube\.com/watch)[^"\']*t=\d+', content))

def add_timestamp_script_and_convert_links(soup, video_id: str) -> bool:
    """Add seekTo JavaScript and convert timestamp links."""
    changed = False
    
    # Find all timestamp links
    timestamp_pattern = re.compile(r'(youtu\.be|youtube\.com/watch).*[?&]t=(\d+)')
    
    for a_tag in soup.find_all('a', href=timestamp_pattern):
        href = a_tag.get('href', '')
        match = re.search(r'[?&]t=(\d+)', href)
        if match:
            seconds = match.group(1)
            # Convert to onclick with seekTo function
            a_tag['href'] = '#'
            a_tag['onclick'] = f"seekToTime({seconds}); return false;"
            a_tag['style'] = a_tag.get('style', '') + 'cursor: pointer; color: #65a30d;'
            changed = True
    
    # Add the seekTo script if we made changes
    if changed:
        # Check if script already exists
        existing_script = soup.find('script', string=re.compile(r'function seekToTime'))
        if not existing_script:
            script_content = f'''
function seekToTime(seconds) {{
    const iframe = document.querySelector('.video-container iframe, iframe[src*="youtube.com/embed"]');
    if (iframe) {{
        // Scroll to video first
        iframe.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        
        // Update iframe src to seek to timestamp and autoplay
        const baseUrl = 'https://www.youtube.com/embed/{video_id}';
        const newSrc = baseUrl + '?start=' + seconds + '&autoplay=1&playsinline=1&rel=0';
        
        setTimeout(() => {{
            iframe.src = newSrc;
        }}, 500);
    }}
}}
'''
            new_script = soup.new_tag('script')
            new_script.string = script_content
            
            # Insert at end of body
            body = soup.find('body')
            if body:
                body.append(new_script)
    
    return changed

def fix_quickview_file(filepath: Path) -> bool:
    """Fix a single quickview HTML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if this file has timestamp links
        if not has_timestamp_links(content):
            print(f"  ⏭️  No timestamp links: {filepath.name}")
            return False
        
        # Parse HTML
        soup = BeautifulSoup(content, 'html.parser')
        
        # Get video ID from iframe
        video_id = extract_video_id_from_iframe(soup)
        if not video_id:
            print(f"  ⚠️  No YouTube iframe found: {filepath.name}")
            return False
        
        print(f"  🎬 Found videoId: {video_id} in {filepath.name}")
        
        # Convert links and add script
        if add_timestamp_script_and_convert_links(soup, video_id):
            # Write back
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            
            print(f"  🔧 Fixed: {filepath.name}")
            return True
        else:
            print(f"  ⏭️  No changes needed: {filepath.name}")
            return False
        
    except Exception as e:
        print(f"  ❌ Error processing {filepath.name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("🔧 Quickview Timestamp Link Fixer")
    print("=" * 60)
    print(f"Directory: {QUICKVIEW_DIR}")
    print("")
    
    if not QUICKVIEW_DIR.exists():
        print("❌ Quickview directory not found!")
        return
    
    html_files = list(QUICKVIEW_DIR.glob("*.html"))
    html_files = [f for f in html_files if f.name != "index.html"]
    
    print(f"Found {len(html_files)} quickview files to check...\n")
    
    fixed_count = 0
    for filepath in sorted(html_files):
        if fix_quickview_file(filepath):
            fixed_count += 1
    
    print("")
    print("=" * 60)
    print(f"✅ Done! Fixed {fixed_count} files.")
    print("=" * 60)

if __name__ == "__main__":
    main()
