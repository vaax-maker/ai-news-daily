#!/usr/bin/env python3
"""
Process Blogger queue and post to Blogger.
Called by GitHub Actions.
Processes potentially multiple queue files matching the pattern.
"""
import os
import json
import sys
import glob
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

WEBSHARE_DIR = PROJECT_ROOT / 'docs' / 'webshare'
QUEUE_PATTERN = str(WEBSHARE_DIR / '.blogger_queue_*.json')


def process_blogger_queue():
    """Process pending Blogger posts from all matching queue files."""
    queue_files = glob.glob(QUEUE_PATTERN)
    
    if not queue_files:
        print("No Blogger queue files found.")
        return
    
    print(f"Found {len(queue_files)} queue files.")
    
    try:
        from src.utils.blogger_client import post_to_blogger, is_blogger_configured
        
        if not is_blogger_configured():
            print("❌ Blogger not configured (missing blogger_credentials.json)")
            return
            
        total_posted = 0
    
        for queue_file_path in queue_files:
            try:
                print(f"Processing: {queue_file_path}")
                with open(queue_file_path, 'r', encoding='utf-8') as f:
                    queue = json.load(f)
                
                if not queue.get('posts'):
                    print("⚠️ Skipping empty queue file.")
                    os.remove(queue_file_path)
                    continue
                
                failed_count = 0
                for post in queue['posts']:
                    title = post.get('title', 'Untitled')
                    html = post.get('html', '')
                    
                    if not html:
                        print(f"⚠️ Skipping empty post: {title}")
                        continue
                    
                    try:
                        print(f"📝 Posting to Blogger: {title}")
                        result = post_to_blogger(title, html)
                        blogger_url = result.get('url')
                        print(f"✅ Posted: {blogger_url}")
                        total_posted += 1
                    except Exception as e:
                        print(f"❌ Failed to post '{title}': {e}")
                        failed_count += 1
                
                if failed_count == 0:
                    # Delete processed file only if no failures
                    os.remove(queue_file_path)
                    print(f"Deleted queue file: {queue_file_path}")
                else:
                    print(f"⚠️ Kept queue file due to {failed_count} failures: {queue_file_path}")
                
            except Exception as e:
                print(f"❌ Error processing file {queue_file_path}: {e}")
                # Continue with other files even if one fails
        
        print(f"\n🎉 Processed {total_posted} posts from {len(queue_files)} files")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        # Build fails if critical error
        sys.exit(1)


if __name__ == '__main__':
    process_blogger_queue()
