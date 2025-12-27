#!/usr/bin/env python3
"""
기존 AI/XR daily HTML 페이지에 3개 액션 버튼을 추가합니다.
"""

import os
import re
from bs4 import BeautifulSoup

def add_action_buttons_to_html(html_path):
    """HTML 파일에 액션 버튼 추가"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        modified = False
        
        # 모든 news-item 찾기
        for article in soup.find_all('article', class_='news-item'):
            # 이미 news-actions가 있으면 건너뛰기
            if article.find('div', class_='news-actions'):
                continue
            
            # 제목과 링크 정보 추출
            title_element = article.find('h2', class_='news-title')
            if not title_element:
                continue
            
            link = title_element.find('a')
            if not link:
                continue
            
            article_title = link.get_text(strip=True)
            article_link = link.get('href', '#')
            
            # 출처 추출
            source_link = article.find('a', class_='source-link')
            source_name = source_link.get_text(strip=True) if source_link else '출처'
            
            # URL 인코딩
            from urllib.parse import quote
            encoded_title = quote(article_title)
            encoded_link = quote(article_link)
            encoded_source = quote(source_name)
            
            # 액션 버튼 HTML 생성
            actions_html = f'''        
        <div class="news-actions">
            <a href="../board/index.html?mode=discuss&title={encoded_title}&link={encoded_link}&source={encoded_source}" 
               class="action-btn discuss-btn">
                💬 토론하기
            </a>
            <button onclick="navigator.clipboard.writeText('{article_link}').then(() => alert('링크가 클립보드에 복사되었습니다!')).catch(() => alert('복사 실패'))" 
                    class="action-btn share-btn">
                🔗 공유
            </button>
            <a href="{article_link}" 
               target="_blank" 
               rel="noopener noreferrer"
               class="action-btn source-btn">
                📑 원문 보기
            </a>
        </div>'''
            
            # 마지막 자식으로 추가
            actions_soup = BeautifulSoup(actions_html, 'html.parser')
            article.append(actions_soup)
            modified = True
        
        if modified:
            # HTML 파일 저장
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True
        return False
        
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        return False

def patch_daily_pages():
    """모든 daily 페이지에 버튼 추가"""
    print("AI/XR Daily 페이지 패치 시작...")
    
    total_patched = 0
    
    for category in ['ai', 'xr']:
        daily_dir = f'docs/{category}/daily'
        
        if not os.path.exists(daily_dir):
            print(f"  ⚠️  {category} daily 디렉토리가 없습니다.")
            continue
        
        html_files = [f for f in os.listdir(daily_dir) if f.endswith('.html')]
        
        for html_file in sorted(html_files):
            html_path = os.path.join(daily_dir, html_file)
            
            if add_action_buttons_to_html(html_path):
                total_patched += 1
                print(f"  ✓ {category.upper()}: {html_file}")
    
    print(f"\n✨ 총 {total_patched}개 페이지 패치 완료!")

if __name__ == "__main__":
    patch_daily_pages()
