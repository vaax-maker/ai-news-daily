#!/usr/bin/env python3
"""
모든 템플릿에서 제목 옆 inline-actions 제거
"""
import re

templates = [
    'templates/daily_list.html',
    'templates/member_page.html', 
    'templates/member_index.html',
    'templates/archive_index.html'
]

for template_path in templates:
    print(f"Processing {template_path}...")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # HTML 템플릿에서 inline-actions span 제거
    content = re.sub(
        r'\s*<span class="inline-actions">.*?</span>',
        '',
        content,
        flags=re.DOTALL
    )
    
    # JavaScript에서 inlineActions 관련 코드 제거
    content = re.sub(
        r'// Inline actions.*?title\.appendChild\(inlineActions\);',
        '',
        content,
        flags=re.DOTALL
    )
    
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ {template_path} 완료")

print("\n✨ 모든 템플릿에서 inline-actions 제거 완료!")
