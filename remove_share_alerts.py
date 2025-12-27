#!/usr/bin/env python3
"""
모든 템플릿에서 공유 버튼의 alert 제거
"""
import re
import os

templates = [
    'templates/daily_list.html',
    'templates/gov_archive.html',
    'templates/member_page.html',
    'templates/member_index.html',
    'templates/archive_index.html'
]

for template_path in templates:
    if not os.path.exists(template_path):
        print(f"  ⚠️  {template_path} 없음")
        continue
        
    print(f"Processing {template_path}...")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # HTML 템플릿의 alert 제거
    # 패턴 1: .then(() => alert('...')).catch(() => alert('...'))
    content = re.sub(
        r"\.then\(\(\) => alert\('링크가 클립보드에 복사되었습니다!'\)\)\.catch\(\(\) => alert\('복사 실패'\)\)",
        "",
        content
    )
    
    # 패턴 2: .then(() => { ... })
    content = re.sub(
        r"\.then\(\(\) =>\s*\{\s*alert\('링크가 클립보드에 복사되었습니다!'\)\s*\}\)\.catch\(\(\) =>\s*\{\s*alert\('복사 실패'\)\s*\}\)",
        "",
        content
    )
    
    # JavaScript 파일 내의 alert 제거
    content = re.sub(
        r"\.then\(\(\) => alert\('링크가 클립보드에 복사되었습니다!'\)\)\s*\.catch\(\(\) => alert\('복사 실패'\)\)",
        "",
        content
    )
    
    if content != original_content:
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ {template_path} 완료")
    else:
        print(f"  - {template_path} 변경사항 없음")

print("\n✨ 모든 템플릿에서 공유 버튼 alert 제거 완료!")
