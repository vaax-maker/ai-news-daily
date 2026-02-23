#!/usr/bin/env python3
"""정부과제 및 나라장터 연동 상태 확인 스크립트"""

import os
import sys
import logging
from datetime import datetime

# Add current directory to path
sys.path.append(os.getcwd())

from src.fetchers.gov import (
    fetch_msit_announcements, 
    fetch_koneps_announcements, 
    fetch_gov_announcements,
    DEFAULT_GOV_API_KEY
)

# 로그 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def print_section(title):
    """섹션 구분선 출력"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_msit():
    """과기정통부 API 테스트"""
    print_section("1. 과기정통부(MSIT) 사업공고 API 테스트")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    print(f"API Key: {api_key[:10]}...")
    
    try:
        results = fetch_msit_announcements(api_key, limit=10)
        
        print(f"\n✓ 성공: {len(results)}개의 공고를 찾았습니다.")
        
        if results:
            print("\n📋 최근 공고 목록 (최대 5개):")
            for i, item in enumerate(results[:5], 1):
                print(f"\n{i}. {item['title']}")
                print(f"   📅 날짜: {item['date']}")
                print(f"   🏢 부서: {item['dept']}")
                print(f"   🔗 링크: {item['link'][:50]}...")
        else:
            print("\n⚠️ 검색 결과가 없습니다.")
            print("   - 최근 공고가 없거나")
            print("   - API 키 승인 문제일 수 있습니다.")
        
        return len(results) > 0
        
    except Exception as e:
        print(f"\n✗ 실패: {e}")
        logger.exception("MSIT API 호출 중 오류")
        return False

def test_koneps():
    """나라장터 API 테스트"""
    print_section("2. 나라장터(KONEPS) 입찰공고 API 테스트")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    print(f"API Key: {api_key[:10]}...")
    
    # 검색 키워드 표시
    keywords = ["인공지능", "AI", "메타버스", "XR", "가상현실", "증강현실", "디지털트윈"]
    print(f"검색 키워드: {', '.join(keywords)}")
    print("검색 기간: 최근 2일")
    
    try:
        results = fetch_koneps_announcements(api_key, limit=20)
        
        print(f"\n✓ 성공: {len(results)}개의 공고를 찾았습니다.")
        
        if results:
            print("\n📋 최근 입찰공고 목록 (최대 5개):")
            for i, item in enumerate(results[:5], 1):
                print(f"\n{i}. {item['title']}")
                print(f"   📅 날짜: {item['date']}")
                print(f"   🏢 기관: {item['dept']}")
                print(f"   🔗 링크: {item['link'][:50]}...")
        else:
            print("\n⚠️ 검색 결과가 없습니다.")
            print("   가능한 원인:")
            print("   1. 최근 2일간 관련 키워드가 포함된 입찰공고가 없음")
            print("   2. API 키 승인 문제 (data.go.kr에서 확인 필요)")
            print("   3. API 서비스 일시적 오류")
            print("   4. API 버전 변경 가능성")
        
        return len(results) > 0
        
    except Exception as e:
        print(f"\n✗ 실패: {e}")
        logger.exception("KONEPS API 호출 중 오류")
        return False

def test_integrated():
    """통합 API 테스트"""
    print_section("3. 통합 정부과제 수집 테스트")
    
    try:
        results = fetch_gov_announcements(limit=50)
        
        print(f"\n✓ 성공: 총 {len(results)}개의 공고를 수집했습니다.")
        
        # 출처별 통계
        sources = {}
        for item in results:
            source = item.get('source_name', '미분류')
            sources[source] = sources.get(source, 0) + 1
        
        print("\n📊 출처별 통계:")
        for source, count in sources.items():
            print(f"   - {source}: {count}개")
        
        if results:
            print("\n📋 통합 공고 목록 (최대 5개):")
            for i, item in enumerate(results[:5], 1):
                print(f"\n{i}. [{item['source_name']}] {item['title']}")
                print(f"   📅 날짜: {item['date']}")
                print(f"   🏢 기관: {item['dept']}")
        
        return len(results) > 0
        
    except Exception as e:
        print(f"\n✗ 실패: {e}")
        logger.exception("통합 API 호출 중 오류")
        return False

def main():
    """메인 테스트 실행"""
    print("\n" + "🚀 정부과제 및 나라장터 연동 상태 확인")
    print(f"📅 테스트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 각 API 테스트
    msit_ok = test_msit()
    koneps_ok = test_koneps()
    integrated_ok = test_integrated()
    
    # 최종 결과
    print_section("최종 결과")
    
    print(f"\n1. 과기정통부 API: {'✅ 정상' if msit_ok else '❌ 실패'}")
    print(f"2. 나라장터 API: {'✅ 정상' if koneps_ok else '⚠️ 데이터 없음'}")
    print(f"3. 통합 수집: {'✅ 정상' if integrated_ok else '❌ 실패'}")
    
    # 전체 상태
    if msit_ok or koneps_ok:
        print(f"\n🎉 전체 상태: 정상 동작 중")
        print("   최소 1개 이상의 API가 정상 작동하고 있습니다.")
    else:
        print(f"\n⚠️ 전체 상태: 확인 필요")
        print("   API 키 또는 서비스 상태를 확인해주세요.")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
