"""Government Announcements Fetcher - 나라장터 및 과기정통부 API"""

import os
import logging
import requests
import datetime
import xml.etree.ElementTree as ET
from typing import List, Dict
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# API Key (환경변수 또는 기본값)
DEFAULT_GOV_API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
REQUEST_TIMEOUT = 30


def fetch_msit_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """
    과학기술정보통신부 사업공고 API 호출
    
    API: http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList
    """
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
        
        logger.info(f"[Gov] MSIT API 성공: {len(items_list)}건 수집")
            
    except Exception as e:
        logger.error(f"[Gov] MSIT API 오류: {e}")
        
    return items_list


def fetch_koneps_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """
    나라장터(조달청) 입찰공고 API 호출
    
    새 엔드포인트: https://apis.data.go.kr/1230000/ad/BidPublicInfoService
    - getBidPblancListInfoThngPPSSrch: 물품 입찰공고
    - getBidPblancListInfoServcPPSSrch: 용역 입찰공고
    """
    
    # 새로운 API 엔드포인트 (2025년 기준)
    base_url = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
    
    # 물품과 용역 모두 검색
    operations = [
        "getBidPblancListInfoServcPPSSrch",  # 용역
        "getBidPblancListInfoThngPPSSrch",   # 물품
    ]
    
    # AI/XR 관련 키워드
    keywords = ["인공지능", "AI", "메타버스", "XR", "가상현실", "증강현실", "디지털트윈", "빅데이터", "클라우드"]
    
    # 검색 기간: 최근 7일
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d") + "2359"
    start_dt = (now - datetime.timedelta(days=7)).strftime("%Y%m%d") + "0000"
    
    items_list = []
    seen_links = set()
    
    for operation in operations:
        for keyword in keywords:
            url = f"{base_url}/{operation}"
            
            params = {
                "serviceKey": service_key,
                "numOfRows": 10,
                "pageNo": 1,
                "inqryDiv": "1",  # 공고일 기준
                "inqryBgnDt": start_dt,
                "inqryEndDt": end_dt,
                "bidNm": keyword,
                "type": "json"
            }
            
            try:
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                
                if response.status_code != 200:
                    logger.warning(f"[KONEPS] HTTP {response.status_code} for {keyword}")
                    continue
                
                data = response.json()
                
                # 응답 구조 확인
                resp = data.get("response", {})
                header = resp.get("header", {})
                result_code = header.get("resultCode", "")
                
                if result_code != "00":
                    logger.warning(f"[KONEPS] API 오류: {header.get('resultMsg', 'Unknown')}")
                    continue
                
                body = resp.get("body", {})
                items = body.get("items", [])
                
                if not items:
                    continue
                
                # items가 리스트가 아닐 경우 처리
                if isinstance(items, dict):
                    items = [items]
                
                for item in items:
                    link = item.get("bidNtceDtlUrl", "")
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    
                    # 날짜 포맷팅
                    raw_date = item.get("bidNtceDt", "")
                    if len(raw_date) >= 8:
                        fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                    else:
                        fmt_date = raw_date
                    
                    items_list.append({
                        "title": item.get("bidNtceNm", ""),
                        "link": link,
                        "dept": item.get("dminsttNm", "") or item.get("ntceInsttNm", "") or "조달청",
                        "manager": item.get("ntceInsttOfclNm", ""),
                        "date": fmt_date,
                        "source_name": "나라장터",
                        "image_url": "",
                        "published_display": fmt_date,
                        "bid_type": "용역" if "Servc" in operation else "물품"
                    })
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"[KONEPS] 네트워크 오류: {e}")
            except ValueError as e:
                logger.error(f"[KONEPS] JSON 파싱 오류: {e}")
            except Exception as e:
                logger.error(f"[KONEPS] 예외 발생: {e}")
    
    # 날짜순 정렬 (최신순)
    items_list.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    logger.info(f"[Gov] 나라장터 API 완료: {len(items_list)}건 수집")
    return items_list[:limit]


def fetch_gov_announcements(limit: int = 50) -> List[Dict[str, str]]:
    """
    정부 과제 통합 수집 (과기정통부 + 나라장터)
    
    Returns:
        List[Dict]: 정부과제 목록
    """
    service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    logger.info("[Gov] 정부과제 통합 수집 시작")
    
    # 1. 과기정통부 사업공고
    msit_items = fetch_msit_announcements(service_key, limit=30)
    
    # 2. 나라장터 입찰공고
    koneps_items = fetch_koneps_announcements(service_key, limit=30)
    
    # 통합 및 정렬
    all_items = msit_items + koneps_items
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    logger.info(f"[Gov] 통합 수집 완료: 과기정통부 {len(msit_items)}건 + 나라장터 {len(koneps_items)}건 = 총 {len(all_items)}건")
    
    return all_items[:limit]


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("정부과제 API 테스트")
    print("=" * 60)
    
    results = fetch_gov_announcements(limit=20)
    
    print(f"\n총 {len(results)}건 수집됨\n")
    
    for i, item in enumerate(results[:10], 1):
        print(f"{i}. [{item['source_name']}] {item['title'][:50]}...")
        print(f"   날짜: {item['date']} | 기관: {item['dept']}")
        print(f"   링크: {item['link'][:60]}...")
        print()
