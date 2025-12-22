#!/usr/bin/env python3
"""나라장터 API 확장 테스트 (검색 기간을 늘려서 테스트)"""

import os
import sys
import logging
import requests
import datetime
from urllib.parse import urlencode

# Add current directory to path
sys.path.append(os.getcwd())

from src.fetchers.gov import DEFAULT_GOV_API_KEY

# 로그 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_koneps_extended(days_back=7, limit=20):
    """나라장터 API 확장 테스트 (검색 기간 조정)"""
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    print("="*60)
    print("나라장터(KONEPS) 입찰공고 API - 확장 테스트")
    print("="*60)
    print(f"\nAPI Key: {api_key[:10]}...")
    print(f"검색 기간: 최근 {days_back}일")
    
    # API 엔드포인트 목록
    endpoints = [
        ("v04 (용역)", "http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch"),
        ("v03", "http://apis.data.go.kr/1230000/BidPublicInfoService03/getBidPblancListInfoServcPPSSrch"),
        ("v02", "http://apis.data.go.kr/1230000/BidPublicInfoService02/getBidPblancListInfoServcPPSSrch"),
    ]
    
    # 검색 키워드
    keywords = ["인공지능", "AI", "메타버스", "XR", "가상현실", "증강현실", "디지털트윈"]
    print(f"검색 키워드: {', '.join(keywords)}\n")
    
    # 날짜 범위 설정
    now = datetime.datetime.now()
    end_dt = now.strftime("%Y%m%d") + "2359"
    start_dt = (now - datetime.timedelta(days=days_back)).strftime("%Y%m%d") + "0000"
    
    print(f"기간: {start_dt} ~ {end_dt}\n")
    
    total_results = []
    seen_links = set()
    
    # 각 API 버전별로 테스트
    for version, url in endpoints:
        print(f"\n{'='*60}")
        print(f"테스트 중: {version}")
        print(f"URL: {url}")
        print('='*60)
        
        keyword_results = []
        
        for keyword in keywords:
            params = {
                "serviceKey": api_key,
                "numOfRows": limit,
                "pageNo": 1,
                "inqryDiv": "1",
                "inqryBgnDt": start_dt,
                "inqryEndDt": end_dt,
                "bidNm": keyword,
                "type": "json"
            }
            
            qs = urlencode({k: v for k, v in params.items() if k != "serviceKey"}, safe="=")
            full_url = f"{url}?serviceKey={api_key}&{qs}"
            
            try:
                print(f"\n🔍 키워드 '{keyword}' 검색 중...", end=" ")
                response = requests.get(full_url, timeout=30)
                
                print(f"상태: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"   ❌ HTTP {response.status_code} 오류")
                    continue
                
                data = response.json()
                
                # 응답 구조 확인
                if "response" not in data:
                    print(f"   ⚠️ 응답 구조 이상: {list(data.keys())}")
                    continue
                
                response_data = data.get("response", {})
                header = response_data.get("header", {})
                result_code = header.get("resultCode", "")
                result_msg = header.get("resultMsg", "")
                
                print(f"   결과 코드: {result_code} - {result_msg}")
                
                body = response_data.get("body", {})
                items = body.get("items", [])
                total_count = body.get("totalCount", 0)
                
                print(f"   📊 총 {total_count}건 중 {len(items)}건 조회")
                
                for item in items:
                    link = item.get("bidNtceDtlUrl", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        
                        raw_date = item.get("bidNtceDt", "")
                        fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) >= 8 else raw_date
                        
                        result = {
                            "title": item.get("bidNtceNm", ""),
                            "link": link,
                            "dept": item.get("daminsttNm", "") or "조달청",
                            "date": fmt_date,
                            "keyword": keyword,
                            "version": version
                        }
                        keyword_results.append(result)
                        total_results.append(result)
                
            except Exception as e:
                print(f"   ❌ 오류: {e}")
                logger.exception(f"키워드 '{keyword}' 검색 중 오류")
        
        print(f"\n📋 {version} 결과: {len(keyword_results)}건")
        
        # 이 버전에서 결과가 있으면 상세 표시
        if keyword_results:
            print("\n최신 공고 5건:")
            for i, item in enumerate(keyword_results[:5], 1):
                print(f"\n{i}. {item['title']}")
                print(f"   📅 날짜: {item['date']}")
                print(f"   🏢 기관: {item['dept']}")
                print(f"   🔍 키워드: {item['keyword']}")
    
    # 최종 결과
    print("\n" + "="*60)
    print("최종 결과")
    print("="*60)
    print(f"\n✅ 총 {len(total_results)}건의 고유한 입찰공고를 찾았습니다.\n")
    
    if total_results:
        # 키워드별 통계
        keyword_stats = {}
        for item in total_results:
            kw = item['keyword']
            keyword_stats[kw] = keyword_stats.get(kw, 0) + 1
        
        print("📊 키워드별 통계:")
        for kw, count in sorted(keyword_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {kw}: {count}건")
        
        print("\n📋 전체 공고 목록 (최대 10건):")
        for i, item in enumerate(total_results[:10], 1):
            print(f"\n{i}. {item['title']}")
            print(f"   📅 날짜: {item['date']}")
            print(f"   🏢 기관: {item['dept']}")
            print(f"   🔍 키워드: {item['keyword']}")
            print(f"   🔗 링크: {item['link'][:60]}...")
    else:
        print("⚠️ 검색 결과가 없습니다.")
        print("\n가능한 원인:")
        print("1. 해당 기간 동안 관련 키워드가 포함된 입찰공고가 없음")
        print("2. API 키 승인 문제 (data.go.kr에서 확인 필요)")
        print("3. API 서비스 변경 또는 중단")
        print("\n해결 방법:")
        print("1. data.go.kr에서 API 키 활성화 상태 확인")
        print("2. 'BidPublicInfoService' 서비스 승인 여부 확인")
        print("3. 검색 기간을 더 늘려보기 (현재: {days_back}일)")
    
    print("\n" + "="*60 + "\n")
    
    return total_results

if __name__ == "__main__":
    # 7일간의 데이터로 테스트
    results = test_koneps_extended(days_back=7, limit=20)
    
    if not results:
        print("\n🔄 30일로 기간을 확장하여 재시도...\n")
        results = test_koneps_extended(days_back=30, limit=30)
