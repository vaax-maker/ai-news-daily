import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def check_status():
    try:
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if not sa_json:
            print("FIREBASE_SERVICE_ACCOUNT not set in .env")
            return

        if not firebase_admin._apps:
            if sa_json.startswith('{'):
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as f:
                    f.write(sa_json)
                    cred = credentials.Certificate(f.name)
            else:
                cred = credentials.Certificate(sa_json)
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        docs = db.collection("admin_notifications").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(5).get()
        
        print("\n--- Recent Notifications ---")
        for doc in docs:
            d = doc.to_dict()
            print(f"ID: {doc.id}")
            print(f"  Status: {d.get('status')}")
            print(f"  Type: {d.get('type')}")
            print(f"  Body: {d.get('body')[:50]}...")
            print(f"  Created: {d.get('createdAt')}")
            if d.get('error'):
                print(f"  Error: {d.get('error')}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error checking status: {e}")

if __name__ == "__main__":
    check_status()
