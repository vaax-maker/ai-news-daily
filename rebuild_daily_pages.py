#!/usr/bin/env python3
"""
AI/XR daily 페이지를 기존 데이터로 다시 생성합니다.
"""

import os
import json
from src.generators.html import render_daily_page
from src.config import load_categories

def rebuild_daily_pages():
    """기존 데이터로 daily HTML 페이지 재생성"""
    print("AI/XR Daily 페이지 재생성 시작...")
    
    categories = load_categories()
    rebuilt_count = 0
    
    for key in ["ai", "xr"]:
        config = categories.get(key)
        if not config:
            continue
            
        daily_dir = f"docs/{key}/daily"
        data_dir = f"data/{key}"
        
        if not os.path.exists(data_dir):
            print(f"  ⚠️  {key} 데이터 디렉토리가 없습니다.")
            continue
            
        # 데이터 파일 찾기
        data_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
        
        for data_file in sorted(data_files, reverse=True):
            data_path = os.path.join(data_dir, data_file)
            
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                
                # 파일명에서 날짜와 시간 추출
                filename = data_file.replace(".json", "")
                parts = filename.split("_")
                
                if len(parts) != 2:
                    continue
                    
                date_str, time_str = parts
                
                # HTML 생성
                html = render_daily_page(
                    articles=articles,
                    date_str=date_str,
                    time_str=time_str,
                    config=config
                )
                
                # HTML 파일 저장
                html_filename = f"{date_str}_{time_str}.html"
                html_path = os.path.join(daily_dir, html_filename)
                
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                
                rebuilt_count += 1
                print(f"  ✓ {key.upper()}: {html_filename}")
                
            except Exception as e:
                print(f"  ✗ {data_file} 처리 실패: {e}")
    
    print(f"\n✨ 총 {rebuilt_count}개 페이지 재생성 완료!")

if __name__ == "__main__":
    rebuild_daily_pages()
