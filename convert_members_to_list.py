#!/usr/bin/env python3
"""
회원사 인덱스를 목록형으로 완전히 변경
"""
import re

with open('templates/member_index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 최신 뉴스 섹션을 카드형에서 목록형으로 변경
old_grid = r'<div class="member-news-grid" id="latest-news-grid">.*?</div>\s*<div id="latest-no-results"'

new_list = '''<div class="simple-news-list" id="latest-news-list">
            {% for item in all_news %}
            <div class="news-list-item search-target" data-search="{{ item.title }} {{ item.member_name }}">
                <div class="list-item-content">
                    <div class="item-badge">{{ item.member_name }}</div>
                    <h3 class="list-item-title">
                        <a href="{{ item.link }}" target="_blank" rel="noopener">{{ item.title }}</a>
                    </h3>
                    <div class="list-item-meta">
                        <span class="meta-source">{{ item.source_name or '출처' }}</span>
                        <span class="meta-date">{{ item.published_display }}</span>
                    </div>
                </div>
                <div class="list-item-actions">
                    <a href="../board/index.html?mode=discuss&title={{ item.title|urlencode }}&link={{ item.link|urlencode }}&source={{ item.source_name|urlencode }}" 
                       class="discuss-btn-sm">토론</a>
                    <button onclick="navigator.clipboard.writeText('{{ item.link }}')" 
                            class="discuss-btn-sm">공유</button>
                </div>
            </div>
            {% endfor %}
        </div>
        <div id="latest-no-results"'''

content = re.sub(old_grid, new_list, content, flags=re.DOTALL)

with open('templates/member_index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ member_index.html을 목록형으로 변경 완료")
