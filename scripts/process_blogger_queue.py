#!/usr/bin/env python3
"""
Process Blogger queue and post to Blogger.
Called by GitHub Actions.
"""
import os
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

QUEUE_FILE = PROJECT_ROOT / 'docs' / 'webshare' / '.blogger_queue.json'


def process_blogger_queue():
    """Process pending Blogger posts from queue."""
    if not QUEUE_FILE.exists():
        print("No Blogger queue file found.")
        return
    
    try:
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            queue = json.load(f)
        
        if not queue.get('posts'):
            print("No posts in queue.")
            QUEUE_FILE.unlink()  # Delete empty queue file
            return
        
        from src.utils.blogger_client import post_to_blogger, is_blogger_configured
        
        if not is_blogger_configured():
            print("❌ Blogger not configured (missing blogger_credentials.json)")
            return
        
        posted_urls = []
        
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
                posted_urls.append({'title': title, 'url': blogger_url})
            except Exception as e:
                print(f"❌ Failed to post '{title}': {e}")
        
        # Delete queue file after processing
        QUEUE_FILE.unlink()
        print(f"\n🎉 Processed {len(posted_urls)} posts to Blogger")
        
    except Exception as e:
        print(f"❌ Error processing queue: {e}")
        raise


if __name__ == '__main__':
    process_blogger_queue()
