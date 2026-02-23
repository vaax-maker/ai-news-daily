#!/usr/bin/env python3
"""
Rebuild member pages with updated templates
"""

import os
import re
import datetime
from src.generators.html import render_member_page, render_member_index, render_archive_index
from src.config import CategoryConfig, load_members
from src.utils.storage import MemberStorage

def rebuild_member_pages():
    """회원사 페이지와 인덱스만 재생성"""
    print("회원사 페이지 재생성 시작...")
    
    # 회원사 정보 로드
    members = load_members()
    storage = MemberStorage()
    
    member_page_dir = "docs/members"
    os.makedirs(member_page_dir, exist_ok=True)
    
    member_entries = []
    all_latest_news = []
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
    
    # 각 회원사별 페이지 생성
    for m_key, member in members.items():
        try:
            # 뉴스 히스토리 로드
            history = storage.load_news(m_key)
            history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            # 개별 페이지 생성
            now_str = datetime.datetime.now().strftime("%Y-%m-%d")
            html = render_member_page(member, history, now_str)
            
            # 파일명 생성
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', m_key).strip()
            page_filename = f"{safe_name}.html"
            
            # 파일 저장
            with open(os.path.join(member_page_dir, page_filename), "w", encoding="utf-8") as f:
                f.write(html)
            
            print(f"✓ {member.name} 페이지 재생성 완료 ({len(history)}건)")
            
            # 인덱스용 데이터 수집
            latest_str = "-"
            latest_title = ""
            latest_link = ""
            
            if history:
                latest = history[0]
                ts = latest.get("timestamp", 0)
                if ts:
                    dt = datetime.datetime.fromtimestamp(ts)
                    wd = weekday_map[dt.weekday()]
                    latest_str = f"{dt.strftime('%Y-%m-%d')}({wd}) {dt.strftime('%H:%M')}"
                else:
                    latest_str = latest.get("published_display", "-")
                latest_title = latest.get("title", "")
                latest_link = latest.get("link", "")
            
            member_entries.append({
                "filename": page_filename,
                "name": member.name,
                "count": len(history),
                "latest_date": latest_str,
                "latest_title": latest_title,
                "latest_link": latest_link
            })
            
            # 전체 뉴스에 최근 뉴스 추가
            all_latest_news.extend(history[:2])
            
        except Exception as e:
            print(f"✗ {member.name} 페이지 생성 실패: {e}")
    
    # 회원사 목록 정렬 (기사 수 내림차순)
    member_entries.sort(key=lambda x: (-x["count"], x["name"]))
    
    # 최신 뉴스 정렬
    all_latest_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    # 오늘 뉴스만 추출
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_start = datetime.datetime.strptime(today_str, "%Y-%m-%d").timestamp()
    todays_news = [
        item for item in all_latest_news 
        if item.get("timestamp", 0) >= today_start
    ]
    
    print(f"전체 뉴스: {len(all_latest_news)}건, 오늘 뉴스: {len(todays_news)}건")
    
    # 인덱스 HTML 생성
    index_html = render_member_index(member_entries, all_news=todays_news)
    
    # 인덱스 파일 저장
    index_path = "docs/members/index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    
    print(f"✓ 회원사 인덱스 페이지 재생성 완료")

def rebuild_archive_pages():
    """아카이브 인덱스 페이지 재생성"""
    print("\n아카이브 페이지 재생성 시작...")
    
    configs = [
        CategoryConfig(
            key="ai",
            display_name="AI 뉴스",
            rss_feeds=[],
            archive_dir="docs/ai/daily",
            index_path="docs/ai/index.html"
        ),
        CategoryConfig(
            key="xr",
            display_name="XR 뉴스",
            rss_feeds=[],
            archive_dir="docs/xr/daily",
            index_path="docs/xr/index.html"
        ),
    ]
    
    for config in configs:
        # 일별 파일 목록 가져오기
        daily_dir = os.path.join("docs", config.key, "daily")
        if not os.path.exists(daily_dir):
            print(f"디렉토리가 없습니다: {daily_dir}")
            continue
            
        # HTML 파일 목록 가져오기
        html_files = [f for f in os.listdir(daily_dir) if f.endswith(".html")]
        
        # 파일명에서 날짜 정보 추출
        run_entries = []
        for filename in html_files:
            # 파일명 형식: YYYY-MM-DD_HHMMSS.html
            parts = filename.replace(".html", "").split("_")
            if len(parts) == 2:
                date_str = parts[0]
                time_str = parts[1]
                
                # 요일 계산
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    day_of_week = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
                except:
                    day_of_week = ""
                
                # 시간 포맷팅 (HHMMSS -> HH:MM:SS)
                if len(time_str) == 6:
                    time_str = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
                
                run_entries.append({
                    "date_str": date_str,
                    "time_str": time_str,
                    "day_of_week": day_of_week,
                    "filename": filename
                })
        
        # HTML 생성
        index_html = render_archive_index(run_entries, config)
        
        # 파일 저장
        index_path = os.path.join("docs", config.key, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_html)
        
        print(f"✓ {config.display_name} 아카이브 페이지 재생성 완료")

if __name__ == "__main__":
    rebuild_member_pages()
    rebuild_archive_pages()
    print("\n✓ 모든 페이지 재생성 완료!")
