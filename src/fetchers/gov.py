"""Government Announcements Fetcher - 나라장터 및 과기정통부 API"""

import os
import logging
import requests
import datetime
import xml.etree.ElementTree as ET
from typing import List, Dict
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# API Key
DEFAULT_GOV_API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
REQUEST_TIMEOUT = 30


def fetch_msit_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """과학기술정보통신부 사업공고 API"""
    url = "http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
    
    params = {
        "serviceKey": service_key,
        "numOfRows": limit,
        "pageNo": 1,
        "type": "xml"
    }
    
    items_list = []
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
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
        
        logger.info(f"[MSIT] 수집 완료: {len(items_list)}건")
            
    except Exception as e:
        logger.error(f"[MSIT] 오류: {e}")
        
    return items_list


def fetch_koneps_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """
    나라장터 입찰공고 API (2025년 최신 엔드포인트)
    
    Base URL: http://apis.data.go.kr/1230000/ad/BidPublicInfoService
    """
    
    base_url = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
    
    # 사용할 operation: PPS 검색 (나라장터 검색조건 활용)
    operations = {
        "용역": "getBidPblancListInfoServcPPSSrch",
        "물품": "getBidPblancListInfoThngPPSSrch",
        "공사": "getBidPblancListInfoCnstwkPPSSrch",
    }
    
    # AI/XR 관련 키워드
    keywords = ["인공지능", "AI", "메타버스", "XR", "가상현실", "증강현실", "디지털트윈"]
    
    # 검색 기간: 최근 7일
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d%H%M")
    start_dt = (now - datetime.timedelta(days=7)).strftime("%Y%m%d") + "0000"
    
    items_list = []
    seen_links = set()
    
    for bid_type, operation in operations.items():
        for keyword in keywords:
            url = f"{base_url}/{operation}"
            
            params = {
                "serviceKey": service_key,
                "numOfRows": 10,
                "pageNo": 1,
                "inqryDiv": "1",      # 공고일 기준
                "inqryBgnDt": start_dt,
                "inqryEndDt": end_dt,
                "bidNtceNm": keyword,  # 입찰공고명 검색
                "type": "json"
            }
            
            try:
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                
                if response.status_code != 200:
                    continue
                
                # JSON 파싱
                try:
                    data = response.json()
                except:
                    # JSON이 아니면 skip
                    continue
                
                # 응답 구조 확인
                resp = data.get("response", {})
                header = resp.get("header", {})
                result_code = header.get("resultCode", "")
                
                if result_code != "00":
                    continue
                
                body = resp.get("body", {})
                items = body.get("items", [])
                
                if not items:
                    continue
                
                # items가 딕셔너리면 리스트로 변환
                if isinstance(items, dict):
                    items = [items]
                
                for item in items:
                    link = item.get("bidNtceDtlUrl", "")
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    
                    # 날짜 파싱: API는 "2025-12-16 09:34:08" 형식으로 반환
                    raw_date = item.get("bidNtceDt", "")
                    if raw_date and " " in raw_date:
                        # "2025-12-16 09:34:08" -> "2025-12-16"
                        fmt_date = raw_date.split()[0]
                    else:
                        fmt_date = raw_date
                    
                    items_list.append({
                        "title": item.get("bidNtceNm", ""),
                        "link": link,
                        "dept": item.get("dminsttNm", "") or item.get("ntceInsttNm", "") or "조달청",
                        "manager": item.get("ntceInsttOfclNm", ""),
                        "date": fmt_date,
                        "source_name": f"나라장터({bid_type})",
                        "image_url": "",
                        "published_display": fmt_date
                    })
                    
            except Exception as e:
                logger.debug(f"[KONEPS] {keyword} 검색 오류: {e}")
                continue
    
    # 날짜순 정렬 (최신순)
    items_list.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    logger.info(f"[KONEPS] 수집 완료: {len(items_list)}건")
    return items_list[:limit]


def fetch_gov_announcements(limit: int = 50) -> List[Dict[str, str]]:
    """정부 과제 통합 수집"""
    service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    # 1. 과기정통부
    msit_items = fetch_msit_announcements(service_key, limit=30)
    
    # 2. 나라장터
    koneps_items = fetch_koneps_announcements(service_key, limit=30)
    
    # 통합 및 정렬 (최신순)
    all_items = msit_items + koneps_items
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    total = len(all_items)
    logger.info(f"[Gov] 통합 수집: 과기정통부 {len(msit_items)}건 + 나라장터 {len(koneps_items)}건 = 총 {total}건")
    
    return all_items[:limit]


# 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = fetch_gov_announcements(limit=20)
    
    print(f"\n총 {len(results)}건 수집\n")
    for i, item in enumerate(results[:10], 1):
        print(f"{i}. [{item['source_name']}] {item['title'][:50]}")
        print(f"   {item['date']} | {item['dept']}\n")
