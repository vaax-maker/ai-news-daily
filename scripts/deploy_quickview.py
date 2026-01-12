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

def main():
    print("\n🚀 [1/3] Generating Quickview Pages...")
    try:
        process_quickview_pages()
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
