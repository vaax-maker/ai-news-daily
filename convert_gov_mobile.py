#!/usr/bin/env python3
"""
정부과제 모바일 카드를 일반 목록형으로 교체
"""

with open('templates/gov_archive.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 모바일 카드 섹션 전체를 찾아서 목록형으로 교체
import re

# gov-cards 전체 섹션 찾기
pattern = r'<div class="gov-cards">.*?</div>\s*{% endfor %}\s*</div>'

replacement = '''<div class="gov-mobile-list">
    {% for item in announcements %}
    <div class="gov-list-item">
        <div class="list-item-header">
            <h3 class="list-item-title">
                <a href="{{ item.link }}" target="_blank" rel="noopener">{{ item.title }}</a>
            </h3>
        </div>
        <div class="list-item-meta">
            <span class="meta-item"><strong>소속:</strong> {{ item.source_name or item.dept or '-' }}</span>
            <span class="meta-item"><strong>담당:</strong> {{ item.manager or '-' }}</span>
            <span class="meta-item"><strong>등록일:</strong> {{ item.date or item.published_display }}</span>
        </div>
        <div class="list-item-schedule">
            {% if item.bid_begin_dt %}
            <span class="schedule-item">입찰시작: {{ item.bid_begin_dt[:16] }}</span>
            <span class="schedule-item">입찰마감: {{ item.bid_close_dt[:16] }}</span>
            {% endif %}
        </div>
        <div class="list-item-actions">
            <a href="../board/index.html?mode=discuss&title={{ item.title|urlencode }}&link={{ item.link|urlencode }}&source={{ item.source_name|urlencode }}" 
               class="discuss-btn-sm">토론</a>
            <button onclick="navigator.clipboard.writeText('{{ item.link }}').then(() => alert('링크가 클립보드에 복사되었습니다!')).catch(() => alert('복사 실패'))" 
                    class="discuss-btn-sm">공유</button>
        </div>
    </div>
    {% endfor %}
</div>'''

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('templates/gov_archive.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ 정부과제 모바일을 목록형으로 변경 완료!")
