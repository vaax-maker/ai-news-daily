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
                "source_name": "과기정통부",  # 통일
                "image_url": "",
                "published_display": item.findtext("pressDt", ""),
                "bid_begin_dt": "",    # 과기정통부는 미제공
                "bid_close_dt": "",    # 과기정통부는 미제공
                "openg_dt": ""         # 과기정통부는 미제공
            })
        
        logger.info(f"[MSIT] 수집 완료: {len(items_list)}건")
            
    except Exception as e:
        logger.error(f"[MSIT] 오류: {e}")
        
    return items_list


def is_relevant_ai_xr_project(title: str) -> bool:
    """
    AI/XR 기술 프로젝트 여부 판단
    
    제외 대상:
    - 단순 물품 구매 (서버, 장비, 설비)
    - 시설 관리/유지보수
    - 일반 행사/홍보
    """
    title_lower = title.lower()
    
    # 제외 키워드 (우선순위 높음)
    EXCLUDE_KEYWORDS = [
        '유지관리', '유지보수', '청소', '경비', '시설관리',
        '설비', '장비 구매', '물품 구매', '납품',
        '인쇄', '간행물', '홍보물', '현수막',
        '무인회수기', '자판기', 'CCTV 설치',
        '보안카메라', '네트워크 장비',
        '일반 서버', '스토리지 구매',
        # 단순 홍보/행사 영상 제외
        '수료식 영상', '성과 영상', '홍보 영상 제작 용역',
        '실시간 중계 용역', '행사 중계'
    ]
    
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return False
    
    # 포함해야 할 핵심 키워드
    INCLUDE_KEYWORDS = [
        # AI 관련
        '인공지능 개발', '머신러닝', '딥러닝', 'AI 모델', 'AI 기술',
        '자연어처리', '컴퓨터비전', 'AI 플랫폼', 'AI 서비스 개발',
        '데이터 분석', '빅데이터 분석',
        
        # XR 관련  
        '메타버스 개발', 'VR 콘텐츠', 'AR 콘텐츠', 'XR 콘텐츠',
        '가상현실 개발', '증강현실 개발', '디지털트윈 구축',
        '3D 모델링', '실감콘텐츠', '실감미디어',
        
        # 영상/미디어 관련 (기술 중심)
        '영상콘텐츠 제작', '뉴미디어 콘텐츠', '미디어 플랫폼',
        '영상 기술', 'OTT 플랫폼', '스트리밍 서비스', 'AI 영상',
        '소셜미디어 콘텐츠', '온라인 교육 콘텐츠', '이러닝',
        
        # IDC 및 인프라
        'IDC', '데이터센터', '클라우드 인프라', '네트워크 구축',
        '서버 구축', 'HPC', '고성능 컴퓨팅', '인프라 구축',
        
        # R&D 및 기술개발
        '기술개발', '연구개발', 'R&D', '실증사업',
        '플랫폼 개발', '시스템 개발', '솔루션 개발',
        '스마트시티', 'IoT', '클라우드 서비스',
        '블록체인', '양자', 'GPU 활용'
    ]
    
    for keyword in INCLUDE_KEYWORDS:
        if keyword.lower() in title_lower:
            return True
    
    # 포함 키워드가 없으면 제외
    return False


def fetch_koneps_announcements(service_key: str, limit: int = 30) -> List[Dict[str, str]]:
    """나라장터 입찰공고 API (AI/XR 기술과제만 필터링)"""
    
    # 기존 작동하는 API 엔드포인트 유지
    base_url = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
    
    # 용역만 검색 (물품/공사는 단순 구매가 많음)
    operations = {
        "용역": "getBidPblancListInfoServcPPSSrch",
    }
    
    # AI/XR/영상/IDC 핵심 키워드
    keywords = [
        "인공지능 개발", "머신러닝", "딥러닝",
        "메타버스", "가상현실", "증강현실", "디지털트윈",
        "XR 콘텐츠", "실감콘텐츠", "실감미디어",
        "영상콘텐츠", "뉴미디어", "미디어 플랫폼",
        "IDC", "데이터센터", "클라우드"
    ]
    
    # 검색 기간: 최근 30일로 확대 (안정적인 데이터 수집)
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d%H%M")
    start_dt = (now - datetime.timedelta(days=30)).strftime("%Y%m%d") + "0000"
    
    items_list = []
    seen_links = set()
    
    for bid_type, operation in operations.items():
        for keyword in keywords:
            url = f"{base_url}/{operation}"
            
            params = {
                "serviceKey": service_key,
                "numOfRows": 10,
                "pageNo": 1,
                "inqryDiv": "1",
                "inqryBgnDt": start_dt,
                "inqryEndDt": end_dt,
                "bidNtceNm": keyword,
                "type": "json"
            }
            
            try:
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                
                if response.status_code != 200:
                    continue
                
                try:
                    data = response.json()
                except:
                    continue
                
                resp = data.get("response", {})
                header = resp.get("header", {})
                result_code = header.get("resultCode", "")
                
                if result_code != "00":
                    continue
                
                body = resp.get("body", {})
                items = body.get("items", [])
                
                if not items:
                    continue
                
                if isinstance(items, dict):
                    items = [items]
                
                for item in items:
                    link = item.get("bidNtceDtlUrl", "")
                    title = item.get("bidNtceNm", "")
                    
                    if not link or not title or link in seen_links:
                        continue
                    
                    # AI/XR 관련성 필터링
                    if not is_relevant_ai_xr_project(title):
                        logger.debug(f"[KONEPS] 필터링 제외: {title[:50]}...")
                        continue
                    
                    seen_links.add(link)
                    
                    # 날짜 파싱
                    raw_date = item.get("bidNtceDt", "")
                    if raw_date and " " in raw_date:
                        fmt_date = raw_date.split()[0]
                    else:
                        fmt_date = raw_date
                    
                    # 입찰 일정 정보 추가
                    bid_begin = item.get("bidBeginDt", "")  # 입찰시작
                    bid_close = item.get("bidClseDt", "")   # 입찰마감
                    openg = item.get("opengDt", "")         # 개찰
                    
                    items_list.append({
                        "title": title,
                        "link": link,
                        "dept": item.get("dminsttNm", "") or item.get("ntceInsttNm", "") or "조달청",
                        "manager": item.get("ntceInsttOfclNm", ""),
                        "date": fmt_date,
                        "source_name": f"나라장터({bid_type})",
                        "image_url": "",
                        "published_display": fmt_date,
                        "bid_begin_dt": bid_begin,    # 입찰시작일시
                        "bid_close_dt": bid_close,    # 입찰마감일시
                        "openg_dt": openg             # 개찰일시
                    })
                    
            except Exception as e:
                logger.debug(f"[KONEPS] {keyword} 검색 오류: {e}")
                continue
    
    items_list.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    logger.info(f"[KONEPS] 수집 완료: {len(items_list)}건 (필터링 후)")
    return items_list[:limit]


def fetch_iitp_announcements(limit: int = 20) -> List[Dict[str, str]]:
    """IITP 정보통신기획평가원 사업공고 스크래핑"""
    from bs4 import BeautifulSoup
    
    url = "https://www.iitp.kr/kr/1/notice/businessAnnouncements.it"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AINewsDailyBot/1.0)"}
    
    items_list = []
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # IITP 공고 목록 파싱
        rows = soup.select("table.board-list tbody tr, ul.board-list > li")
        
        for row in rows[:limit]:
            # 제목/링크 추출
            title_el = row.select_one("a")
            if not title_el:
                continue
            
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            
            # 상대 경로를 절대 경로로 변환
            if href and not href.startswith("http"):
                link = f"https://www.iitp.kr{href}"
            else:
                link = href
            
            # 날짜 추출
            date_el = row.select_one("td.date, span.date, .regist-date")
            date = date_el.get_text(strip=True) if date_el else ""
            
            # AI/XR 관련성 필터링
            if not is_relevant_ai_xr_project(title):
                continue
            
            items_list.append({
                "title": title,
                "link": link,
                "dept": "IITP",
                "manager": "",
                "date": date,
                "source_name": "IITP",
                "image_url": "",
                "published_display": date,
                "bid_begin_dt": "",
                "bid_close_dt": "",
                "openg_dt": ""
            })
        
        logger.info(f"[IITP] 수집 완료: {len(items_list)}건")
        
    except Exception as e:
        logger.error(f"[IITP] 오류: {e}")
    
    return items_list


def fetch_nia_announcements(limit: int = 20) -> List[Dict[str, str]]:
    """NIA 한국지능정보사회진흥원 입찰공고 스크래핑"""
    from bs4 import BeautifulSoup
    
    # NIA 입찰공고 페이지 (API 형태로 호출)
    url = "https://www.nia.or.kr/site/nia_kor/ex/bbs/List.do"
    params = {
        "cbIdx": "82106",  # 입찰공고 게시판 ID
        "sdate": "",
        "edate": "",
        "searchCnd": "0",
        "searchWrd": ""
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AINewsDailyBot/1.0)",
        "Referer": "https://www.nia.or.kr"
    }
    
    items_list = []
    try:
        response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        
        # NIA는 접근 제한이 있을 수 있음
        if response.status_code != 200:
            logger.warning(f"[NIA] 접근 제한: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # NIA 공고 목록 파싱
        rows = soup.select("table tbody tr, ul.board-list > li")
        
        for row in rows[:limit]:
            title_el = row.select_one("a")
            if not title_el:
                continue
            
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            
            if href and not href.startswith("http"):
                link = f"https://www.nia.or.kr{href}"
            else:
                link = href
            
            date_el = row.select_one("td.date, span.date")
            date = date_el.get_text(strip=True) if date_el else ""
            
            # AI/XR 관련성 필터링
            if not is_relevant_ai_xr_project(title):
                continue
            
            items_list.append({
                "title": title,
                "link": link,
                "dept": "NIA",
                "manager": "",
                "date": date,
                "source_name": "NIA",
                "image_url": "",
                "published_display": date,
                "bid_begin_dt": "",
                "bid_close_dt": "",
                "openg_dt": ""
            })
        
        logger.info(f"[NIA] 수집 완료: {len(items_list)}건")
        
    except Exception as e:
        logger.error(f"[NIA] 오류: {e}")
    
    return items_list


def fetch_gov_announcements(limit: int = 50) -> List[Dict[str, str]]:
    """정부 과제 통합 수집 (과기정통부 + 나라장터 + IITP + NIA)"""
    service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    # 1. 과기정통부
    msit_items = fetch_msit_announcements(service_key, limit=30)
    
    # 2. 나라장터
    koneps_items = fetch_koneps_announcements(service_key, limit=30)
    
    # 3. IITP (정보통신기획평가원)
    iitp_items = fetch_iitp_announcements(limit=20)
    
    # 4. NIA (한국지능정보사회진흥원)
    nia_items = fetch_nia_announcements(limit=20)
    
    # 통합 및 중복 제거
    seen_links = set()
    all_items = []
    
    for item in msit_items + koneps_items + iitp_items + nia_items:
        link = item.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            all_items.append(item)
    
    # 날짜 정렬
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    logger.info(f"[Gov] 통합 수집: 과기정통부 {len(msit_items)}건 + 나라장터 {len(koneps_items)}건 + IITP {len(iitp_items)}건 + NIA {len(nia_items)}건 = 총 {len(all_items)}건")
    
    return all_items[:limit]


# 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = fetch_gov_announcements(limit=30)
    
    print(f"\n총 {len(results)}건 수집\n")
    for i, item in enumerate(results[:15], 1):
        print(f"{i}. [{item['source_name']}] {item['title'][:60]}")
        print(f"   {item['date']} | {item['dept']}\n")

