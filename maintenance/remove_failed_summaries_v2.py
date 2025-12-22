
import os
import glob
from bs4 import BeautifulSoup
import sys

# 프로젝트 루트 디렉토리 설정 (절대 경로)
BASE_DIR = "/Users/fovea/Documents/vsc-codex/VAAXfinal"

def clean_failed_summaries(category):
    search_path = os.path.join(BASE_DIR, f"docs/{category}/daily/*.html")
    files = glob.glob(search_path)
    
    print(f"[{category.upper()}] Scanning {len(files)} files in {search_path}...")
    
    total_removed = 0
    total_files_modified = 0

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 텍스트가 아예 없으면 빠르게 스킵
        if "요약 실패" not in content and "Summarization failed" not in content:
            continue

        soup = BeautifulSoup(content, 'html.parser')
        modified = False
        items_to_remove = []

        # 여러 컨테이너 선택자 시도
        # 1. article.news-card (Tile style)
        # 2. article.news-item (List style in raw HTMLs)
        # 3. li.news-item
        containers = soup.select('article.news-card, article.news-item, li.news-item, .news-tile')

        for item in containers:
            text = item.get_text().strip()
            # 정확한 실패 문구 확인
            if "요약 실패" in text or "Summarization failed" in text:
                items_to_remove.append(item)

        if items_to_remove:
            for item in items_to_remove:
                item.decompose()
                total_removed += 1
            modified = True

        # 만약 컨테이너가 하나도 안 남았다면 "기사 없음" 메시지를 추가하면 좋겠지만, 
        # 일단은 비어있게 놔둠 (나중에 재생성되길 기대하거나 그대로 유지)

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            total_files_modified += 1
            # print(f"  Fixed: {os.path.basename(filepath)} (-{len(items_to_remove)})")

    print(f"[{category.upper()}] Removed {total_removed} items across {total_files_modified} files.\n")

if __name__ == "__main__":
    clean_failed_summaries("ai")
    clean_failed_summaries("xr")
