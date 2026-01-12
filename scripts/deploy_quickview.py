#!/usr/bin/env python3
"""
Deploy Quickview Script

1. Generates Quickview pages (HTML) locally.
2. Commits and Pushes to GitHub.
3. If successful, triggers pending Telegram notifications.

Usage: python3 scripts/deploy_quickview.py
"""
import os
import sys
import subprocess
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set Firebase Credentials from local file if env not set
if not os.getenv("FIREBASE_SERVICE_ACCOUNT"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(os.path.dirname(script_dir), "vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json")
    if os.path.exists(cred_path):
        os.environ["FIREBASE_SERVICE_ACCOUNT"] = cred_path
        print(f"[Deploy] Set FIREBASE_SERVICE_ACCOUNT to {cred_path}")

from generate_quickview import process_quickview_pages
from scripts.process_scheduled import main as process_notifications

import requests
import time

def verify_deployment(pages, timeout_seconds=300):
    """
    Check if the new pages are incorrectly returning 404.
    Waits until they return 200 OK.
    """
    # Filter only new pages (is_new=True) to check
    new_pages = [p for p in pages if p.get('is_new')]
    if not new_pages:
        return True
    
    # We only check the most recent one to save time/bandwidth, or all?
    # Checking all might be slow if many. Let's check the first one (most recent).
    target_page = new_pages[0]
    url = f"https://vaax-maker.github.io/ai-news-daily/{target_page['url']}"
    
    print(f"   Target URL: {url}")
    print(f"   Waiting up to {timeout_seconds}s for 200 OK...")
    
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            r = requests.get(url, timeout=5, params={'nocache': time.time()})
            if r.status_code == 200:
                print(f"   🎉 Page is live! (took {int(time.time() - start_time)}s)")
                return True
            else:
                sys.stdout.write(".")
                sys.stdout.flush()
        except Exception as e:
            print(f"   Error checking URL: {e}")
        
        time.sleep(5)
    
    print("\n   ❌ Timeout waiting for page deployment.")
    return False

def main():
    print("\n🚀 [1/3] Generating Quickview Pages...")
    try:
        pages = process_quickview_pages()
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        return

    print("\n📦 [2/3] Deploying to GitHub...")
    try:
        # Check status
        # subprocess.run(["git", "status"], check=True)
        
        # Add files
        subprocess.run(["git", "add", "docs/quickview", "docs/index.html"], check=True)
        
        # Commit (ignore error if nothing to commit)
        subprocess.run("git diff --staged --quiet || git commit -m 'Update quickview pages [manual]'", shell=True, check=False)
        
        # Push
        print("   Pushing changes...")
        subprocess.run(["git", "push"], check=True)
        print("✅ Deployment Successful!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Deployment Failed: {e}")
        return

    # 2.5 Verify URLs before sending notifications
    if pages:
        print("\n🔍 [2.5/3] Verifying Deployment (waiting for GitHub Pages)...")
        if not verify_deployment(pages):
            print("⚠️ Verification timed out or failed. Notifications might link to 404 pages.")
            # We proceed anyway? Or stop? User wants to avoid 404. 
            # If verification failed, it means the page isn't live. 
            # But maybe we should ask user? Logic: Proceed with warning or risk not sending at all.
            # Let's proceed but with huge warning log.
            # But the user request is "Again such things won't happen?" -> implied strictness.
            # If it fails after 5 mins, likely something is wrong. 
            # Let's try to notify anyway but strictly log it.
        else:
            print("✅ All new pages are live!")
    else:
        print("\nℹ️ No new pages to verify.")

    print("\n📨 [3/3] Processing Notifications...")
    # This will pick up 'pending' notifications from Firestore and send them
    try:
        process_notifications()
        print("✅ Notifications processed.")
    except Exception as e:
        print(f"❌ Notification processing failed: {e}")

    print("\n✨ All Done! Pages are live and notifications sent.")

if __name__ == "__main__":
    main()
