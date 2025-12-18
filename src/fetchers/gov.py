"""Government Announcements Fetcher with improved security."""

import os
import logging
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Default API key (fallback) - should be overridden by environment variable
DEFAULT_GOV_API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
REQUEST_TIMEOUT = 30


import os
import logging
import requests
import datetime
import xml.etree.ElementTree as ET
from typing import List, Dict
from urllib.parse import urlencode, quote_plus

logger = logging.getLogger(__name__)

# Default API key (fallback) - should be overridden by environment variable
DEFAULT_GOV_API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
REQUEST_TIMEOUT = 30


def fetch_msit_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """과학기술정보통신부 사업공고 API 호출"""
    url = "http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
    
    params = {
        "serviceKey": service_key,
        "numOfRows": limit,
        "pageNo": 1,
        "type": "xml"
    }
    
    full_url = f"{url}?{urlencode(params, safe='=')}"
    logger.info(f"[Gov] MSIT API 요청: {url}")
    
    items_list = []
    try:
        response = requests.get(full_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        xml_items = root.findall(".//item")
        
        for item in xml_items:
            items_list.append({
                "title": item.findtext("subject", ""),
                "link": item.findtext("viewUrl", ""),
                "dept": item.findtext("deptName", "") or "과기정통부",
                "manager": item.findtext("managerName", ""),
                "date": item.findtext("pressDt", ""),
                "source_name": "과기정통부",
                "image_url": "",
                "published_display": item.findtext("pressDt", "")
            })
            
    except Exception as e:
        logger.error(f"[Gov] MSIT API failed: {e}")
        
    return items_list


def fetch_koneps_announcements(service_key: str, limit: int = 20) -> List[Dict[str, str]]:
    """나라장터(조달청) 입찰공고 API 호출 (용역)"""
    # 입찰공고정보서비스 (용역)
    url = "http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch"
    
    # 검색할 키워드 목록
    keywords = ["인공지능", "AI", "메타버스", "XR", "가상현실", "증강현실", "디지털트윈"]
    
    # 조회 기간: 오늘부터 2일 전까지
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d") + "2359"
    start_dt = (now - datetime.timedelta(days=2)).strftime("%Y%m%d") + "0000"
    
    items_list = []
    seen_links = set()

    for keyword in keywords:
        params = {
            "serviceKey": service_key,
            "numOfRows": int(limit / 2), # 키워드별로 조금씩 가져옴
            "pageNo": 1,
            "inqryDiv": "1", # 1:조회, 2:생략
            "inqryBgnDt": start_dt,
            "inqryEndDt": end_dt,
            "bidNm": keyword, # 공고명 검색
            "type": "json"    # JSON 지원됨
        }
        
        # requests will handle urlencoding
        # Note: serviceKey in data.go.kr often needs to be unquoted if passed in params dict in some libs,
        # but requests usually handles it. However, data.go.kr keys are tricky. 
        # Best to construct query string manually for serviceKey if it contains special chars.
        
        # Using string construction for safety with data.go.kr keys
        qs = urlencode({k: v for k, v in params.items() if k != "serviceKey"}, safe="=")
        full_url = f"{url}?serviceKey={service_key}&{qs}"
        
        try:
            response = requests.get(full_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            body = data.get("response", {}).get("body", {})
            items = body.get("items", [])
            
            if not items:
                continue
                
            for item in items:
                link = item.get("bidNtceDtlUrl", "")
                if link in seen_links:
                    continue
                seen_links.add(link)
                
                # 날짜 포맷팅 (YYYYMMDDHHMM -> YYYY-MM-DD)
                raw_date = item.get("bidNtceDt", "")
                fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) >= 8 else raw_date
                
                items_list.append({
                    "title": item.get("bidNtceNm", ""),
                    "link": link,
                    "dept": item.get("daminsttNm", "") or "조달청", # 수요기관명
                    "manager": "",
                    "date": fmt_date,
                    "source_name": "나라장터",
                    "image_url": "",
                    "published_display": fmt_date
                })
                
        except Exception as e:
            # 키워드 하나 실패해도 계속 진행
            # logger.warning(f"[Gov] KONEPS keyword '{keyword}' failed: {e}")
            pass

    logger.info(f"[Gov] Fetched {len(items_list)} KONEPS announcements")
    return items_list


def fetch_gov_announcements(limit: int = 50) -> List[Dict[str, str]]:
    """
    정부 과제 통합 수집 (과기부 + 나라장터)
    """
    service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    # 1. MSIT
    msit_items = fetch_msit_announcements(service_key, limit=30)
    
    # 2. KONEPS (Nara Market)
    koneps_items = fetch_koneps_announcements(service_key, limit=20)
    
    # Merge and Sort
    all_items = msit_items + koneps_items
    
    # Sort by date desc
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    return all_items[:limit]
