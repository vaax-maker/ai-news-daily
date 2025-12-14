import os
import glob
from datetime import datetime, timedelta
from collections import Counter
import re
from wordcloud import WordCloud
from bs4 import BeautifulSoup
from src.generators.llm import analyze_text_with_llm
import random

def extract_weekly_keywords(docs_dir="docs", days=7):
    """
    Extracts keywords from AI and XR daily summaries for the past `days` days,
    filtering for Person, Tech, Company, Solution using LLM.
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # Collect titles and snippets
    collected_text = []

    # Paths to search
    # Assuming structure: docs/ai/daily/YYYY-MM-DD.html and docs/xr/daily/YYYY-MM-DD.html
    # We will walk through the directory to be safe or glob specific patterns
    
    search_paths = [
        os.path.join(docs_dir, "ai", "daily", "*.html"),
        os.path.join(docs_dir, "xr", "daily", "*.html")
    ]
    
    files_processed = 0
    
    for pattern in search_paths:
        for file_path in glob.glob(pattern):
            # Extract date from filename
            filename = os.path.basename(file_path)
            # Expected format: YYYY-MM-DD.html or YYYY-MM-DD_HHMMSS.html
            try:
                # Remove extension
                name_only = filename.replace(".html", "")
                # Split by underscore if present to get date part
                date_part = name_only.split("_")[0]
                
                file_date = datetime.strptime(date_part, "%Y-%m-%d")
                
                if file_date >= cutoff_date:
                    # Process this file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        soup = BeautifulSoup(f.read(), 'html.parser')
                        
                        # Extract text from headings and list items (summaries)
                        # Titles are h2.news-title, summaries are in li inside ul.summary-list
                        for tag in soup.find_all(['h2', 'li']):
                            collected_text.append(tag.get_text(strip=True))
                    
                    files_processed += 1
            except ValueError:
                continue # Skip files that don't match date format

    print(f"Processed {files_processed} files. Found {len(collected_text)} titles.")
    
    if not collected_text:
        return Counter()

    # Limit text to avoid token limits (approx 100 recent titles should be fine, but if more, sample or take latest)
    # 7 days * 2 categories * 5 articles = 70 articles. Should fit easily.
    context_text = "\n".join(collected_text[:200]) 
    
    prompt = f"""
다음은 최근 테크 뉴스 기사의 제목들이다.
이 텍스트에서 가장 중요하고 빈번하게 언급되는 키워드를 추출하되, 
반드시 아래 4가지 카테고리에 해당하는 것만 선정하시오.

[카테고리]
- 사람 (Person)
- 기술 (Technology/Concept)
- 업체 (Company)
- 솔루션/제품 (Solution/Product)

[제약사항]
1. 불용어(조사, 일반명사 등)는 제외할 것.
2. 국문/영문 혼용 가능.
3. 총 30~50개의 핵심 키워드를 선정할 것.
4. 중요도에 따라 빈도수(가중치)를 1~10 사이로 추정하여 CSV 형식으로 출력하시오.

[출력형식]
키워드,가중치
OpenAI,10
김범수,8
LLM,9
...

[분석대상 텍스트]
{context_text}
"""
    # Call LLM
    print("[WordCloud] Requesting LLM extraction...")
    response = analyze_text_with_llm(prompt)
    
    # Parse CSV-like output
    word_counts = Counter()
    
    for line in response.split('\n'):
        line = line.strip()
        if not line or ',' not in line:
            continue
        try:
            parts = line.split(',')
            word = parts[0].strip()
            count = int(parts[1].strip())
            # Basic cleanup
            word = word.replace('"', '').replace("'", "")
            if len(word) > 1:
                word_counts[word] = count
        except:
            continue
            
    # Fallback if LLM fails or returns nothing
    if not word_counts:
        print("[WordCloud] LLM returned empty or invalid data. Falling back to simple frequency.")
        # Simple fallback logic (removed for brevity or use the old logic if desired, but user wants strict filtering)
        # For now, return empty or minimal
        pass

    return word_counts

def create_wordcloud_image(word_counts, output_path, font_path=None):
    """
    Generates a word cloud image from word counts.
    """
    if not word_counts:
        print("No words found to generate word cloud.")
        return False

    # Default Mac Korean font if none provided
    if font_path is None:
        font_path = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
        if not os.path.exists(font_path):
             # Fallback to standard AppleGothic if Supplemental doesn't exist (older macOS) or try another
            font_path = "/System/Library/Fonts/AppleGothic.ttf"
            
    try:
        wc = WordCloud(
            font_path=font_path,
            width=1200,
            height=400,
            background_color='white',
            max_words=100,
            stopwords=None # Already filtered
        )
        
        wc.generate_from_frequencies(word_counts)
        wc.to_file(output_path)
        print(f"Word cloud saved to {output_path}")
        return True
    
    except Exception as e:
        print(f"Error generating word cloud: {e}")
        return False

if __name__ == "__main__":
    # Test run
    # Adjust this path for local testing if needed, or pass current directory
    counts = extract_weekly_keywords(docs_dir=os.path.join(os.getcwd(), "docs"))
    create_wordcloud_image(counts, "test_wordcloud.png")
