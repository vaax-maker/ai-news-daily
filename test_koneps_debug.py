
import requests
import datetime
from urllib.parse import urlencode

API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
URL = "http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch"

def debug_koneps():
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d") + "2359"
    start_dt = (now - datetime.timedelta(days=7)).strftime("%Y%m%d") + "0000" # 7일로 넉넉하게
    
    keyword = "인공지능"
    
    params = {
        "numOfRows": 5,
        "pageNo": 1,
        "inqryDiv": "1",
        "inqryBgnDt": start_dt,
        "inqryEndDt": end_dt,
        "bidNm": keyword,
        "type": "json",
        "serviceKey": API_KEY  # requests가 인코딩 할 수도 있음
    }
    
    # 1. requests.get params 사용 (자동 인코딩)
    print("--- Attempt 1: requests params (Auto Encoding) ---")
    try:
        res = requests.get(URL, params=params, timeout=10)
        print(f"Status Code: {res.status_code}")
        print(f"Response URL: {res.url}")
        print(f"Response Body Prefix: {res.text[:500]}")
    except Exception as e:
        print(e)
        
    # 2. Manual query string (No Encoding for Key if already encoded?)
    # 키에 %가 없으면 Decoding된 키이므로 인코딩이 필요함.
    print("\n--- Attempt 2: Manual URL Construction ---")
    qs = urlencode({k: v for k, v in params.items() if k != "serviceKey"})
    full_url = f"{URL}?serviceKey={API_KEY}&{qs}"
    try:
        res = requests.get(full_url, timeout=10)
        print(f"Status Code: {res.status_code}")
        print(f"Response Body Prefix: {res.text[:500]}")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    debug_koneps()
