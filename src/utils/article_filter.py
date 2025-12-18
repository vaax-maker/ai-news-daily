"""
Article Filtering Pipeline
권장 구조에 따른 3단계 필터링 시스템

1단계: 휴리스틱 필터 (비용 0)
   - 시간 필터 (24시간)
   - 중복 제거
   - 키워드 필터
   → 100+ → 30개로 축소

2단계: LLM 랭킹 (저비용, 선택적)
   - 제목만 분석
   - 배치 처리
   → 30개 → 상위 10개 선정

3단계: 요약 생성 (선택적)
   - RSS 설명 활용 또는 LLM 요약
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collections import defaultdict

# 중요 키워드 (점수 +)
IMPORTANT_KEYWORDS = {
    # 주요 기업
    'company': ['openai', 'google', 'apple', 'microsoft', 'meta', 'amazon', 
                'nvidia', 'amd', 'samsung', 'lg', '삼성', 'LG', '네이버', '카카오',
                'anthropic', 'deepmind', '구글', 'apple', '애플', 'tesla', '테슬라'],
    # 제품/모델
    'product': ['gpt-5', 'gpt5', 'gemini', 'claude', 'llama', 'o1', 'o3', 
                'copilot', 'sora', 'chatgpt', 'bard', 'mistral', 'deepseek'],
    # 이벤트
    'event': ['출시', '발표', '공개', 'release', 'launch', 'announce', 'reveal',
              '신제품', '신모델', 'upgrade', '업그레이드'],
    # 비즈니스
    'business': ['인수', '합병', 'acquisition', 'merger', '투자', 'investment',
                 'ipo', '규제', 'regulation', '정책', 'policy', '독점', 'antitrust'],
    # 기술 트렌드
    'tech': ['에이전트', 'agent', 'agi', 'robotics', '로봇', '휴머노이드', 
             'humanoid', '자율주행', 'autonomous', '월드모델', 'world model',
             '피지컬', 'physical ai']
}

# 제외 키워드 (점수 -)
NEGATIVE_KEYWORDS = [
    '튜토리얼', 'tutorial', '가이드', 'guide', 'how to', '하는 방법',
    '홍보', 'sponsored', '광고', 'ad', '쿠폰', 'coupon', '할인', 'discount',
    '무료', 'free trial', '체험판'
]

# 출처별 신뢰도 가중치
SOURCE_WEIGHTS = {
    'techcrunch.com': 1.5,
    'technologyreview.com': 1.5,
    'aitimes.com': 1.3,
    'aitimes.kr': 1.3,
    'youtube.com': 1.2,  # YouTube는 약간 낮게
    'news.google.com': 1.0,
    'default': 1.0
}


def get_source_weight(url: str) -> float:
    """URL에서 출처 가중치 반환"""
    for domain, weight in SOURCE_WEIGHTS.items():
        if domain in url.lower():
            return weight
    return SOURCE_WEIGHTS['default']


def calculate_heuristic_score(title: str, url: str = '', description: str = '') -> float:
    """
    휴리스틱 점수 계산 (0-100)
    """
    score = 50.0  # 기본 점수
    text = f"{title} {description}".lower()
    
    # 1. 키워드 점수
    for category, keywords in IMPORTANT_KEYWORDS.items():
        weight = {'company': 8, 'product': 6, 'event': 5, 'business': 5, 'tech': 4}.get(category, 3)
        for kw in keywords:
            if kw.lower() in text:
                score += weight
                break  # 카테고리당 한 번만
    
    # 2. 제외 키워드 감점
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in text:
            score -= 15
            break
    
    # 3. 출처 가중치
    source_weight = get_source_weight(url)
    score *= source_weight
    
    # 4. 제목 길이 보정 (너무 짧거나 길면 감점)
    title_len = len(title)
    if title_len < 15:
        score -= 10
    elif title_len > 100:
        score -= 5
    
    # 5. YouTube 조회수 보너스 (description에 포함된 경우)
    if 'youtube.com' in url.lower():
        views_match = re.search(r'views["\s:]+(\d+)', description)
        if views_match:
            views = int(views_match.group(1))
            if views > 100000:
                score += 15
            elif views > 10000:
                score += 8
            elif views > 1000:
                score += 3
    
    return max(0, min(100, score))


def deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """
    중복 기사 제거
    - 동일 URL 제거
    - 유사 제목 제거 (80% 이상 유사)
    """
    seen_urls = set()
    seen_titles = []
    unique = []
    
    for article in articles:
        url = article.get('link', '')
        title = article.get('title', '')
        
        # URL 중복 체크
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # 제목 유사도 체크 (간단한 방식)
        title_tokens = set(title.lower().split())
        is_duplicate = False
        for seen_title in seen_titles:
            seen_tokens = set(seen_title.lower().split())
            if len(title_tokens) > 0 and len(seen_tokens) > 0:
                overlap = len(title_tokens & seen_tokens) / len(title_tokens | seen_tokens)
                if overlap > 0.7:  # 70% 이상 겹치면 중복
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            seen_titles.append(title)
            unique.append(article)
    
    return unique


def filter_by_time(articles: List[Dict], hours: int = 48) -> List[Dict]:
    """
    시간 기반 필터링
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = []
    
    for article in articles:
        ts = article.get('timestamp', 0)
        if ts:
            article_time = datetime.fromtimestamp(ts)
            if article_time >= cutoff:
                filtered.append(article)
        else:
            # timestamp 없으면 포함 (최신으로 간주)
            filtered.append(article)
    
    return filtered


def first_stage_filter(articles: List[Dict], max_count: int = 30, time_hours: int = 48) -> List[Dict]:
    """
    1단계: 휴리스틱 필터 (비용 0)
    - 시간 필터
    - 중복 제거  
    - 휴리스틱 점수 정렬
    """
    print(f"[Filter] 1단계 시작: {len(articles)}개 기사")
    
    # 1. 시간 필터
    time_filtered = filter_by_time(articles, time_hours)
    print(f"[Filter] 시간 필터 후: {len(time_filtered)}개")
    
    # 2. 중복 제거
    unique = deduplicate_articles(time_filtered)
    print(f"[Filter] 중복 제거 후: {len(unique)}개")
    
    # 3. 휴리스틱 점수 계산 및 정렬
    for article in unique:
        article['heuristic_score'] = calculate_heuristic_score(
            article.get('title', ''),
            article.get('link', ''),
            article.get('summary', '') or article.get('description', '')
        )
    
    # 점수 내림차순 정렬
    sorted_articles = sorted(unique, key=lambda x: x.get('heuristic_score', 0), reverse=True)
    
    result = sorted_articles[:max_count]
    print(f"[Filter] 1단계 완료: {len(result)}개 선정 (상위 점수: {result[0].get('heuristic_score', 0):.1f})" if result else "[Filter] 1단계 완료: 0개")
    
    return result


def second_stage_filter(articles: List[Dict], limit: int = 10, use_llm: bool = False) -> List[Dict]:
    """
    2단계: LLM 랭킹 (선택적)
    - LLM 사용 시: 제목만으로 배치 랭킹
    - LLM 미사용 시: 휴리스틱 점수 기준
    """
    print(f"[Filter] 2단계 시작: {len(articles)}개 → {limit}개 선정")
    
    if not use_llm:
        # 휴리스틱 점수 기준으로 선정
        return articles[:limit]
    
    # LLM 랭킹 (나중에 구현)
    try:
        from src.generators.llm import _rank_with_llm
        # 튜플 형식으로 변환
        tuples = [(a.get('timestamp', 0), a.get('title', ''), a) for a in articles]
        ranked = _rank_with_llm(tuples, limit)
        return [t[2] for t in ranked]
    except Exception as e:
        print(f"[Filter] LLM 랭킹 실패, 휴리스틱 사용: {e}")
        return articles[:limit]


def prepare_summary(article: Dict, use_llm: bool = False) -> str:
    """
    3단계: 요약 준비
    - RSS 설명 활용 (기본)
    - LLM 요약 (선택적)
    """
    # 기존 요약이 있으면 사용
    if article.get('summary'):
        return article['summary']
    
    # description 필드 활용
    description = article.get('description', '')
    if description:
        # 첫 300자 사용
        summary = description[:300]
        if len(description) > 300:
            summary += '...'
        return summary
    
    # LLM 요약 (선택적)
    if use_llm:
        try:
            from src.generators.llm import summarize_article
            return summarize_article(article.get('title', ''), '')
        except Exception:
            pass
    
    return ''


def run_filter_pipeline(articles: List[Dict], 
                        max_first_stage: int = 30,
                        final_limit: int = 10,
                        use_llm_ranking: bool = False,
                        use_llm_summary: bool = False,
                        time_hours: int = 48) -> List[Dict]:
    """
    전체 필터링 파이프라인 실행
    
    Args:
        articles: 원본 기사 목록
        max_first_stage: 1단계 통과 최대 개수 (기본 30)
        final_limit: 최종 선정 개수 (기본 10)
        use_llm_ranking: LLM 랭킹 사용 여부 (기본 False)
        use_llm_summary: LLM 요약 사용 여부 (기본 False)
        time_hours: 시간 필터 범위 (기본 48시간)
    
    Returns:
        필터링 완료된 기사 목록
    """
    print(f"\n{'='*50}")
    print(f"📰 Article Filter Pipeline")
    print(f"{'='*50}")
    print(f"입력: {len(articles)}개 기사")
    
    # 1단계: 휴리스틱 필터 (무료)
    stage1 = first_stage_filter(articles, max_first_stage, time_hours)
    
    # 2단계: 랭킹 (선택적 LLM)
    stage2 = second_stage_filter(stage1, final_limit, use_llm_ranking)
    
    # 3단계: 요약 준비
    for article in stage2:
        if not article.get('summary'):
            article['summary'] = prepare_summary(article, use_llm_summary)
    
    print(f"{'='*50}")
    print(f"✅ 최종 출력: {len(stage2)}개 기사")
    print(f"{'='*50}\n")
    
    return stage2
