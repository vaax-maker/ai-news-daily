#!/usr/bin/env python3
"""
모든 페이지의 액션 버튼을 간소화합니다.
- 원문 보기 제거
- 이모지 제거 (💬 → 토론, 🔗 → 공유)
- 제목 옆으로 이동
"""

import os
import re
from bs4 import BeautifulSoup

def simplify_action_buttons(html_path):
    """HTML 파일의 액션 버튼 간소화"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        modified = False
        
        #AI/XR daily 페이지: news-item 찾기
        for article in soup.find_all('article', class_='news-item'):
            # 기존 news-actions 제거
            actions_div = article.find('div', class_='news-actions')
            if actions_div:
                actions_div.decompose()
                modified = True
            
            # 제목과 링크 찾기
            title_h2 = article.find('h2', class_='news-title')
            if not title_h2:
                continue
                
            title_link = title_h2.find('a')
            if not title_link:
                continue
            
            article_title = title_link.get_text(strip=True)
            article_link = title_link.get('href', '#')
            
            # 출처 찾기
            source_link = article.find('a', class_='source-link')
            source_name = source_link.get_text(strip=True) if source_link else '출처'
            
            # URL 인코딩
            from urllib.parse import quote
            encoded_title = quote(article_title)
            encoded_link = quote(article_link)
            encoded_source = quote(source_name)
            
            # 제목 옆에 인라인 액션 추가
            inline_actions_html = f'''
                <span class="inline-actions">
                    <a href="../board/index.html?mode=discuss&title={encoded_title}&link={encoded_link}&source={encoded_source}" 
                       class="action-link">토론</a>
                    <span class="action-separator">|</span>
                    <button onclick="navigator.clipboard.writeText('{article_link}').then(() => alert('링크가 클립보드에 복사되었습니다!')).catch(() => alert('복사 실패'))" 
                            class="action-link action-button">공유</button>
                </span>
            '''
            
            inline_soup = BeautifulSoup(inline_actions_html, 'html.parser')
            title_h2.append(inline_soup)
            modified = True
        
        if modified:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True
        return False
        
    except Exception as e:
        print(f"  ✗ 오류 ({html_path}): {e}")
        return False

def main():
    print("액션 버튼 간소화 시작...")
    
    total_updated = 0
    
    # AI/XR daily 페이지들
    for category in ['ai', 'xr']:
        daily_dir = f'docs/{category}/daily'
        
        if not os.path.exists(daily_dir):
            continue
        
        html_files = [f for f in os.listdir(daily_dir) if f.endswith('.html')]
        
        for html_file in sorted(html_files):
            html_path = os.path.join(daily_dir, html_file)
            
            if simplify_action_buttons(html_path):
                total_updated += 1
                print(f"  ✓ {category.upper()}: {html_file}")
    
    print(f"\n✨ 총 {total_updated}개 페이지 업데이트 완료!")

if __name__ == "__main__":
    main()
