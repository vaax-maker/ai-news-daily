"""정부과제 데이터 누적 저장 및 관리"""

import os
import json
from typing import List, Dict

GOV_DATA_DIR = "data/gov"
ANNOUNCEMENTS_FILE = os.path.join(GOV_DATA_DIR, "announcements.json")


def load_existing_announcements() -> List[Dict]:
    """기존 저장된 공고 불러오기"""
    if not os.path.exists(ANNOUNCEMENTS_FILE):
        return []
    
    try:
        with open(ANNOUNCEMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Storage] 기존 데이터 로드 실패: {e}")
        return []


def save_announcements(new_items: List[Dict]) -> int:
    """
    새 공고를 기존 데이터와 병합하여 저장
    
    Args:
        new_items: 새로 수집된 공고 목록
        
    Returns:
        추가된 새 항목 수
    """
    os.makedirs(GOV_DATA_DIR, exist_ok=True)
    
    # 기존 데이터 로드
    existing = load_existing_announcements()
    
    # 중복 체크용 (링크 기준)
    existing_links = {item['link'] for item in existing}
    
    # 새 항목만 추가
    new_count = 0
    for item in new_items:
        if item['link'] not in existing_links:
            existing.append(item)
            existing_links.add(item['link'])
            new_count += 1
    
    # 날짜순 정렬 (최신순)
    existing.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    # 저장
    with open(ANNOUNCEMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    print(f"[Storage] 저장 완료: 기존 {len(existing)-new_count}건 + 신규 {new_count}건 = 총 {len(existing)}건")
    
    return new_count


def get_all_announcements() -> List[Dict]:
    """전체 공고 조회 (누적 데이터)"""
    return load_existing_announcements()


def get_stats() -> Dict:
    """통계 정보"""
    items = load_existing_announcements()
    
    if not items:
        return {"total": 0, "sources": {}}
    
    # 출처별 통계
    sources = {}
    for item in items:
        source = item.get('source_name', 'Unknown')
        sources[source] = sources.get(source, 0) + 1
    
    # 날짜 범위
    dates = sorted([item['date'] for item in items if item.get('date')])
    
    return {
        "total": len(items),
        "sources": sources,
        "date_range": {
            "oldest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None
        }
    }


if __name__ == "__main__":
    # 테스트
    stats = get_stats()
    print("📊 현재 저장된 정부과제 통계:")
    print(f"  총 {stats['total']}건")
    print(f"  출처별:")
    for source, count in stats['sources'].items():
        print(f"    - {source}: {count}건")
    if stats['date_range']['oldest']:
        print(f"  기간: {stats['date_range']['oldest']} ~ {stats['date_range']['latest']}")
