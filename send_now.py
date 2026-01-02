#!/usr/bin/env python3
"""
Quick script to manually process pending admin notifications.
Run this when you want immediate delivery without waiting for GitHub Actions.
"""
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set the service account path
script_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["FIREBASE_SERVICE_ACCOUNT"] = os.path.join(
    script_dir,
    "vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json"
)

# Import and run the processor
from scripts.process_scheduled import main

if __name__ == "__main__":
    print("🚀 Processing pending notifications immediately...")
    main()
    print("✅ Done! Check Telegram for messages.")
