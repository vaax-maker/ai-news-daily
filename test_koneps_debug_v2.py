
import requests
import datetime
from urllib.parse import urlencode, quote_plus, unquote

API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"

endpoints = [
    "http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch",
    "http://apis.data.go.kr/1230000/BidPublicInfoService03/getBidPblancListInfoServcPPSSrch",
    "http://apis.data.go.kr/1230000/BidPublicInfoService02/getBidPblancListInfoServcPPSSrch",
]

def debug_koneps_all():
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d") + "2359"
    start_dt = (now - datetime.timedelta(days=3)).strftime("%Y%m%d") + "0000"
    keyword = "AI" # 영문 키워드 시도
    
    # 공공데이터포털 키 처리:
    # 1. 키가 Decoding 상태라면 quote_plus 필요할 수도 있지만 requests params는 알아서 해줌.
    # 2. 키가 이미 Encoding 상태라면 unquote 필요.
    # 현재 키는 Hex String 같으므로 URL Safe함. 그대로 사용.

    print(f"Testing Key: {API_KEY}\n")

    for url in endpoints:
        print(f"Testing URL: {url}")
        
        # XML 요청 (json 파라미터 제거, 안전하게)
        params = {
            "numOfRows": 1,
            "pageNo": 1,
            "inqryDiv": "1",
            "inqryBgnDt": start_dt,
            "inqryEndDt": end_dt,
            "bidNm": keyword,
            "serviceKey": API_KEY
        }
        
        try:
            res = requests.get(url, params=params, timeout=10)
            print(f"  Status: {res.status_code}")
            print(f"  Body: {res.text[:300]}") # 에러 메시지 확인
        except Exception as e:
            print(f"  Error: {e}")
        print("-" * 50)

if __name__ == "__main__":
    debug_koneps_all()
