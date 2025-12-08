import urllib.request
import urllib.parse
import json
import ssl

# API Info
API_URL = "http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
SERVICE_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"

def check_api():
    # Construct params
    # Note: ServiceKey is often tricky. If the provided key is already decoded, we might need to percent-encode it if the server expects it. 
    # Or pass it as is if we build the query string manually.
    
    params = {
        "serviceKey": SERVICE_KEY, 
        "numOfRows": 10,
        "pageNo": 1,
        "type": "json" 
    }
    
    query_string = urllib.parse.urlencode(params, safe="=") 
    # safe="=" is important if key has % and we don't want to double encode, but here key is hex.
    
    full_url = f"{API_URL}?{query_string}"
    print(f"Requesting: {full_url}")
    
    try:
        # Ignore SSL for test if needed (sometimes gov sites have cert issues)
        context = ssl._create_unverified_context()
        
        with urllib.request.urlopen(full_url, context=context) as response:
            status = response.getcode()
            print(f"Status Code: {status}")
            
            body = response.read().decode('utf-8')
            print("Response Text Preview:")
            print(body[:500])
            
            try:
                data = json.loads(body)
                print("\nJSON Parsed Successfully.")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            except:
                print("\nResponse is not JSON.")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_api()
