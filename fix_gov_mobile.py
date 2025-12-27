#!/usr/bin/env python3
"""
정부과제 모바일 카드의 버튼을 테이블과 동일하게 수정
"""
import re

with open('templates/gov_archive.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 모바일 카드의 news-actions 부분을 찾아서 교체
# 패턴: <div class="news-actions">로 시작하는 부분
pattern = r'(<div class="news-actions">.*?토론 토론하기.*?공유 공유.*?원문 보기.*?</div>\s*</div>)'

replacement = '''<div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e2e8f0; display: flex; gap: 0.5rem; justify-content: center;">
            <a href="../board/index.html?mode=discuss&title={{ item.title|urlencode }}&link={{ item.link|urlencode }}&source={{ item.source_name|urlencode }}" 
               class="discuss-btn-sm">토론</a>
            <button onclick="navigator.clipboard.writeText('{{ item.link }}').then(() => alert('링크가 클립보드에 복사되었습니다!')).catch(() => alert('복사 실패'))" 
                    class="discuss-btn-sm">공유</button>
        </div>
</div>'''

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('templates/gov_archive.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ 정부과제 모바일 카드 버튼 스타일 통일 완료!")
