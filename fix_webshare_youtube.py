#!/usr/bin/env python3
"""
Fix YouTube IFrame API usage in webshare pages.
Converts to direct iframe embeds for better compatibility.
"""

import os
import re
from pathlib import Path
from bs4 import BeautifulSoup

WEBSHARE_DIR = Path(__file__).parent / "docs" / "webshare"

def extract_video_id_from_api_script(html_content: str) -> str | None:
    """Extract videoId from YouTube IFrame API script."""
    # Pattern: videoId: 'XXXX' or videoId: "XXXX"
    match = re.search(r"videoId:\s*['\"]([a-zA-Z0-9_-]+)['\"]", html_content)
    if match:
        return match.group(1)
    return None

def has_iframe_api(html_content: str) -> bool:
    """Check if the page uses YouTube IFrame API (not direct iframe)."""
    has_api_script = 'youtube.com/iframe_api' in html_content
    has_player_div = 'id="player"' in html_content or "id='player'" in html_content
    has_direct_iframe = re.search(r'<iframe[^>]+youtube\.com/embed/', html_content) is not None
    
    # Uses API if has API script and player div, but no direct iframe embed
    return has_api_script and has_player_div and not has_direct_iframe

def fix_webshare_file(filepath: Path) -> bool:
    """Fix a single webshare HTML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if this file uses IFrame API
        if not has_iframe_api(content):
            print(f"  ⏭️  Does not use IFrame API: {filepath.name}")
            return False
        
        # Extract video ID
        video_id = extract_video_id_from_api_script(content)
        if not video_id:
            print(f"  ⚠️  Could not find videoId: {filepath.name}")
            return False
        
        print(f"  🎬 Found videoId: {video_id} in {filepath.name}")
        
        # Parse HTML
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find the video container with player div
        player_div = soup.find('div', id='player')
        if not player_div:
            print(f"  ⚠️  Could not find #player div: {filepath.name}")
            return False
        
        # Create new iframe
        new_iframe = soup.new_tag('iframe')
        new_iframe['src'] = f'https://www.youtube.com/embed/{video_id}?playsinline=1&rel=0'
        new_iframe['title'] = 'YouTube video player'
        new_iframe['frameborder'] = '0'
        new_iframe['allow'] = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture'
        new_iframe['allowfullscreen'] = True
        
        # Replace player div with iframe
        player_div.replace_with(new_iframe)
        
        # Remove the YouTube IFrame API script block
        # Find and remove the script that contains onYouTubeIframeAPIReady
        for script in soup.find_all('script'):
            if script.string and 'onYouTubeIframeAPIReady' in script.string:
                # Check if this script has seekTo function
                if 'seekTo' in script.string:
                    # Keep seekTo but remove the API code
                    new_script_content = re.sub(
                        r"//\s*YouTube IFrame API.*?function onPlayerReady\(event\)\s*\{[^}]*\}",
                        "",
                        script.string,
                        flags=re.DOTALL
                    )
                    # Also remove the variable declarations
                    new_script_content = re.sub(
                        r"var tag = document\.createElement.*?firstScriptTag\.parentNode\.insertBefore\(tag, firstScriptTag\);",
                        "",
                        new_script_content,
                        flags=re.DOTALL
                    )
                    new_script_content = re.sub(r"var player;\s*", "", new_script_content)
                    
                    # Update seekTo function to work without API
                    new_script_content = re.sub(
                        r"function seekTo\(seconds\)\s*\{[^}]+if\s*\(player && player\.seekTo\)\s*\{",
                        "function seekTo(seconds) {\n            const iframe = document.querySelector('.video-container iframe');\n            if (iframe) {",
                        new_script_content
                    )
                    new_script_content = re.sub(
                        r"player\.seekTo\(seconds,\s*true\);\s*player\.playVideo\(\);",
                        "iframe.src = iframe.src.split('?')[0] + '?playsinline=1&rel=0&autoplay=1&start=' + seconds;",
                        new_script_content
                    )
                    
                    script.string = new_script_content
                else:
                    # Remove the entire script
                    script.decompose()
        
        # Also remove external API script tag if exists
        for script in soup.find_all('script', src=re.compile(r'youtube\.com/iframe_api')):
            script.decompose()
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        print(f"  🔧 Fixed: {filepath.name}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error processing {filepath.name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("🔧 Webshare YouTube IFrame API Fixer")
    print("=" * 60)
    print(f"Directory: {WEBSHARE_DIR}")
    print("")
    
    if not WEBSHARE_DIR.exists():
        print("❌ Webshare directory not found!")
        return
    
    html_files = list(WEBSHARE_DIR.glob("*.html"))
    html_files = [f for f in html_files if 'index' not in f.name.lower() and 'secret' not in f.name.lower()]
    
    print(f"Found {len(html_files)} webshare files to check...\n")
    
    fixed_count = 0
    for filepath in sorted(html_files):
        if fix_webshare_file(filepath):
            fixed_count += 1
    
    print("")
    print("=" * 60)
    print(f"✅ Done! Fixed {fixed_count} files.")
    print("=" * 60)

if __name__ == "__main__":
    main()
