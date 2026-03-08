import os
import sys
import json
from dotenv import dotenv_values

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    env_vars = dotenv_values(".env")
    
    # Force initialize Firebase with env var payload
    sa_json = env_vars.get("FIREBASE_SERVICE_ACCOUNT")
    if sa_json:
        import tempfile
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        if sa_json.startswith('{'):
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as f:
                f.write(sa_json)
                temp_path = f.name
            cred = credentials.Certificate(temp_path)
        else:
            cred = credentials.Certificate(sa_json)
            
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        
        # Import after init
        from src.generators.quickview import process_quickview_pages, get_latest_quickviews
        
        pages = process_quickview_pages()
        print(f"Total processed pages: {len(pages)}")
        
        latest = get_latest_quickviews()
        print(f"Latest quickviews ({len(latest)}):")
        for idx, page in enumerate(latest):
            print(f"  {idx + 1}. {page['title']} (URL: {page['url']})")
    else:
        print("FIREBASE_SERVICE_ACCOUNT not set in .env")
    print(f"Total processed pages: {len(pages)}")
    
    latest = get_latest_quickviews()
    print(f"Latest quickviews ({len(latest)}):")
    for idx, page in enumerate(latest):
        print(f"  {idx + 1}. {page['title']} (URL: {page['url']})")

if __name__ == "__main__":
    main()
