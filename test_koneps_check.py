
import os
import sys
import logging

# Add current directory to path
sys.path.append(os.getcwd())

from src.fetchers.gov import fetch_koneps_announcements, DEFAULT_GOV_API_KEY

# 로그 설정 (Warning 이상만 표시하여 깔끔하게)
logging.basicConfig(level=logging.WARNING)

def test_koneps():
    # .env 파일 로드 (python-dotenv가 있다면)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    # URL 인코딩 되어 있을 수 있으므로 디코딩 필요 시 처리? 
    # requests가 알아서 처리하거나 key 자체가 이미 디코딩된 상태여야 함.
    # gov.py에서는 urlencode를 쓰고 있음.
    
    print(f"Using API Key: {api_key[:10]}...")
    
    print("Fetching KONEPS (Nara Market) announcements...")
    try:
        results = fetch_koneps_announcements(api_key, limit=10)
        
        print(f"\nFound {len(results)} items.")
        if results:
            print("\nPreview of items:")
            for i, item in enumerate(results[:5]):
                print(f"{i+1}. [{item['date']}] {item['title']}")
                print(f"   Org: {item['dept']}")
                print(f"   Link: {item['link']}")
        else:
            print("\nNo items found. Possible reasons:")
            print("1. API Key authorization failed (Check data.go.kr approval)")
            print("2. No announcements matching keywords in the last 2 days")
            print("3. API service temporary error")
            
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    test_koneps()
