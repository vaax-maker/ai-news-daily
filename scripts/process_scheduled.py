import os
import sys
import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.notifier import TelegramNotifier

load_dotenv()

def main():
    print(f"[{datetime.datetime.now()}] Starting Notification Processor...")
    # 1. Initialize Firebase
    try:
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if sa_json:
            import tempfile
            import json
            # sa_json might be a path or a JSON string
            if sa_json.startswith('{'):
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as f:
                    f.write(sa_json)
                    f_path = f.name
                cred = credentials.Certificate(f_path)
            else:
                cred = credentials.Certificate(sa_json)
        else:
            # Fallback for local or if already configured in environment
            try:
                cred = credentials.ApplicationDefault()
            except:
                print("No Firebase credentials found. Set FIREBASE_SERVICE_ACCOUNT.")
                return
        
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print(f"Firebase init failed: {e}")
        return

    notifier = TelegramNotifier()
    # Use UTC for consistency if Firestore stores it as UTC
    now = datetime.datetime.now(datetime.timezone.utc)

    print(f"Checking for pending notifications at {now}...")

    # 2. Fetch Pending Notifications
    try:
        docs = db.collection("admin_notifications").where("status", "==", "pending").stream()
        found = False

        for doc in docs:
            found = True
            data = doc.to_dict()
            doc_id = doc.id
            
            should_send = False
            notif_type = data.get("type", "immediate")
            
            if notif_type == "immediate":
                should_send = True
            elif notif_type == "queued":
                # Queued messages are sent on the next processor run
                should_send = True
            elif notif_type == "scheduled":
                target_time = data.get("targetTime")
                if target_time:
                    # Firestore returns datetime objects in UTC
                    if target_time <= now:
                        should_send = True
                else:
                    # No target time? Send anyway or skip? Let's skip safely.
                    print(f"Skipping {doc_id}: No targetTime for scheduled type.")

            if should_send:
                print(f"Processing message {doc_id} ({notif_type})...")
                body = data.get("body", "")
                if body:
                    # Prepend [VAAX Notifier] if not already present? 
                    # User requested it for the previous manual test.
                    # I'll let the user decide in the UI, but I can add it if requested.
                    # For now, send as is.
                    success = notifier.send_message(body)
                    if success:
                        db.collection("admin_notifications").document(doc_id).update({
                            "status": "sent",
                            "sentAt": firestore.SERVER_TIMESTAMP
                        })
                        print(f"Successfully sent {doc_id}")
                    else:
                        print(f"Failed to send {doc_id}")
                else:
                    print(f"Empty body for {doc_id}. Marking as error.")
                    db.collection("admin_notifications").document(doc_id).update({
                        "status": "error",
                        "error": "Empty body"
                    })

        if not found:
            print("No pending notifications found.")

    except Exception as e:
        print(f"Error processing notifications: {e}")

if __name__ == "__main__":
    main()
