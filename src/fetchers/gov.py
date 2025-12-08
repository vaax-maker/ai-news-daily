import urllib.request
from urllib.parse import urlencode
import ssl
import xml.etree.ElementTree as ET
from typing import List, Dict

def fetch_gov_announcements(limit: int = 30) -> List[Dict]:
    """과학기술정보통신부 사업공고 API 호출"""
    url = "http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
    # 인증키 (Decoding 불필요한 경우 그대로 사용)
    service_key = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
    
    params = {
        "serviceKey": service_key,
        "numOfRows": limit,
        "pageNo": 1,
        "type": "xml" 
    }
    
    query = urlencode(params, safe="=")
    full_url = f"{url}?{query}"
    
    print(f"[Gov] API 요청: {full_url}")
    
    items_list = []
    try:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(full_url, context=context) as response:
            if response.getcode() != 200:
                print(f"[Gov] API 오류 Code: {response.getcode()}")
                return []
                
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            xml_items = root.findall(".//item")
            
            for item in xml_items:
                subject = item.findtext("subject", "")
                view_url = item.findtext("viewUrl", "")
                dept_name = item.findtext("deptName", "")
                manager_name = item.findtext("managerName", "")
                press_dt = item.findtext("pressDt", "")
                
                items_list.append({
                    "title": subject,
                    "link": view_url,
                    "dept": dept_name,
                    "manager": manager_name,
                    "date": press_dt,
                    "summary": "",
                    "source_name": "과학기술정보통신부",
                    "image_url": "",
                    "published_display": press_dt
                })

    except Exception as e:
        print(f"[Gov] API 호출 실패: {e}")
        
    return items_list
