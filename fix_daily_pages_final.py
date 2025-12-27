#!/usr/bin/env python3
"""
AI/XR daily 페이지들 수정:
1. inline-actions 제거 (제목 옆 토론/공유 제거)
2. alert 제거 (HTML 엔티티 버전 포함)
"""
import os
import re
from bs4 import BeautifulSoup

def fix_daily_page(html_path):
    """HTML 파일 수정"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        modified = False
        
        # 1. inline-actions 제거
        for inline_actions in soup.find_all('span', class_='inline-actions'):
            inline_actions.decompose()
            modified = True
        
        if modified:
            html_str = str(soup)
            
            # 2. alert 제거 (HTML 엔티티 버전)
            html_str = re.sub(
                r"\.then\(\(\) =&gt; alert\('링크가 클립보드에 복사되었습니다!'\)\)\.catch\(\(\) =&gt; alert\('복사 실패'\)\)",
                "",
                html_str
            )
            
            # 3. alert 제거 (일반 버전)
            html_str = re.sub(
                r"\.then\(\(\) => alert\('링크가 클립보드에 복사되었습니다!'\)\)\.catch\(\(\) => alert\('복사 실패'\)\)",
                "",
                html_str
            )
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_str)
            return True
        
        return False
        
    except Exception as e:
        print(f"  ✗ 오류 ({html_path}): {e}")
        return False

def main():
    print("AI/XR daily 페이지 수정 시작...")
    print("  - inline-actions 제거 (제목 옆 토론/공유)")
    print("  - alert 팝업 제거")
    print()
    
    total_updated = 0
    
    # AI/XR daily 페이지들
    for category in ['ai', 'xr']:
        daily_dir = f'docs/{category}/daily'
        
        if not os.path.exists(daily_dir):
            continue
        
        html_files = [f for f in os.listdir(daily_dir) if f.endswith('.html')]
        
        for html_file in sorted(html_files):
            html_path = os.path.join(daily_dir, html_file)
            
            if fix_daily_page(html_path):
                total_updated += 1
                if total_updated <= 10:
                    print(f"  ✓ {category.upper()}: {html_file}")
    
    if total_updated > 10:
        print(f"  ... (나머지 {total_updated - 10}개)")
    
    print(f"\n✨ 총 {total_updated}개 페이지 업데이트 완료!")

if __name__ == "__main__":
    main()
