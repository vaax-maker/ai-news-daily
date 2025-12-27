#!/usr/bin/env python3
"""
AI/XR daily 페이지들의 공유 버튼 alert 제거
"""
import os
import re
from bs4 import BeautifulSoup

def fix_daily_page(html_path):
    """HTML 파일의 공유 버튼 alert 제거"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # alert 제거
        content = re.sub(
            r"\.then\(\(\) => alert\('링크가 클립보드에 복사되었습니다!'\)\)\.catch\(\(\) => alert\('복사 실패'\)\)",
            "",
            content
        )
        
        if content != original_content:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
        
    except Exception as e:
        print(f"  ✗ 오류 ({html_path}): {e}")
        return False

def main():
    print("AI/XR daily 페이지 공유 버튼 alert 제거 시작...")
    
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
                if total_updated <= 10:  # 처음 10개만 출력
                    print(f"  ✓ {category.upper()}: {html_file}")
    
    if total_updated > 10:
        print(f"  ... (나머지 {total_updated - 10}개)")
    
    print(f"\n✨ 총 {total_updated}개 페이지 업데이트 완료!")

if __name__ == "__main__":
    main()
