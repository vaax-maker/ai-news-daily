#!/usr/bin/env python3
"""
회원사 인덱스 템플릿 완전 재작성 및 AI/XR daily 페이지 패치
"""
import os
import re

# 1. 회원사 인덱스 템플릿 수정
print("1. member_index.html 수정 중...")

with open('templates/member_index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 잘못된 span과 button 구조 수정
pattern = r'<h3 class="tile-title">.*?</h3>'

replacement = '''<h3 class="tile-title">
                        <a href="{{ item.link }}" target="_blank" rel="noopener">{{ item.title }}</a>
                    </h3>
                    <div class="tile-meta">
                        <span class="tile-source">{{ item.source_name or '출처' }}</span>
                        <span class="tile-date">{{ item.published_display }}</span>
                    </div>
                    <div class="tile-actions">
                        <a href="../board/index.html?mode=discuss&title={{ item.title|urlencode }}&link={{ item.link|urlencode }}&source={{ item.source_name|urlencode }}" 
                           class="discuss-btn-sm">토론</a>
                        <button onclick="navigator.clipboard.writeText('{{ item.link }}')" 
                                class="discuss-btn-sm">공유</button>
                    </div>'''

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('templates/member_index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("  ✓ member_index.html 완료")

# 2. AI/XR daily 페이지 패치
print("\n2. AI/XR daily 페이지 패치 중...")

from bs4 import BeautifulSoup

def fix_daily_html(html_path):
    """HTML의 잘못된 구조 수정"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        modified = False
        
        # 모든 news-item 찾기
        for article in soup.find_all('article', class_='news-item'):
            news_title = article.find('h2', class_='news-title')
            if not news_title:
                continue
            
            # 잘못 들어간 span/button 제거
            for bad_tag in news_title.find_all(['span', 'button']):
                if bad_tag.get('class') and 'action' in str(bad_tag.get('class')):
                    bad_tag.decompose()
                    modified = True
            
            # 기존 news-actions 제거 (있다면)
            existing_actions = article.find('div', class_='news-actions-bottom')
            if existing_actions:
                existing_actions.decompose()
            
            # 타이틀 링크 가져오기
            title_link = news_title.find('a')
            if not title_link:
                continue
            
            article_link = title_link.get('href', '#')
            article_title = title_link.get_text(strip=True)
            
            # 출처 찾기  
            source_link = article.find('a', class_='source-link')
            source_name = source_link.get_text(strip=True) if source_link else '출처'
            
            # URL 인코딩
            from urllib.parse import quote
            encoded_title = quote(article_title)
            encoded_link = quote(article_link)
            encoded_source = quote(source_name)
            
            # news-actions-bottom 추가
            actions_html = f'''
            <div class="news-actions-bottom">
                <a href="../board/index.html?mode=discuss&title={encoded_title}&link={encoded_link}&source={encoded_source}" 
                   class="discuss-btn-sm">토론</a>
                <button onclick="navigator.clipboard.writeText('{article_link}')" 
                        class="discuss-btn-sm">공유</button>
            </div>
            '''
            
            actions_soup = BeautifulSoup(actions_html, 'html.parser')
            article.append(actions_soup)
            modified = True
        
        if modified:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True
        
        return False
    except Exception as e:
        return False

total_fixed = 0
for category in ['ai', 'xr']:
    daily_dir = f'docs/{category}/daily'
    if not os.path.exists(daily_dir):
        continue
    
    html_files = [f for f in os.listdir(daily_dir) if f.endswith('.html')]
    
    for html_file in sorted(html_files):
        html_path = os.path.join(daily_dir, html_file)
        if fix_daily_html(html_path):
            total_fixed += 1
            if total_fixed <= 5:
                print(f"  ✓ {category.upper()}: {html_file}")

if total_fixed > 5:
    print(f"  ... (나머지 {total_fixed - 5}개)")

print(f"\n✨ 총 {total_fixed}개 페이지 수정 완료!")
