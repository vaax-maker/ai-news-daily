import os
import glob
from datetime import datetime, timedelta
from collections import Counter
import re
from wordcloud import WordCloud
from bs4 import BeautifulSoup
from src.generators.llm import analyze_text_with_llm
import random

def extract_weekly_keywords(docs_dir="docs", days=2):
    """
    Extracts keywords from AI and XR daily summaries for the past `days` days,
    filtering for Person, Tech, Company, Solution using LLM.
    Returns (word_counts, word_to_category).
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
        return Counter(), {}

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
- 상품 (Product): 구체적인 제품, 서비스, 솔루션의 이름

[제약사항]
1. 불용어(조사, 일반명사 등)는 제외할 것.
2. **절대 포함하지 말 것**: AI, LLM, llm, ai, 인공지능, 인공 지능 (이들은 너무 일반적임)
3. "ChatGPT", "Gemini", "Claude" 같은 구체적인 AI 제품명은 포함 가능
4. 국문/영문 혼용 가능.
5. 총 30~50개의 핵심 키워드를 선정할 것.
6. 카테고리명은 반드시 Person, Technology, Company, Product 중 하나로 출력할 것.
7. 중요도에 따라 빈도수(가중치)를 1~10 사이로 추정하여 CSV 형식으로 출력하시오.

[출력형식]
카테고리,키워드,가중치
Company,OpenAI,10
Person,김범수,8
Technology,트랜스포머,9
Product,ChatGPT,10
...

[분석대상 텍스트]
{context_text}
"""
    # Call LLM
    print("[WordCloud] Requesting LLM extraction...")
    response = analyze_text_with_llm(prompt)
    
    # Parse CSV-like output
    word_counts = Counter()
    word_to_category = {}
    
    for line in response.split('\n'):
        line = line.strip()
        if not line or ',' not in line:
            continue
        try:
            parts = line.split(',')
            if len(parts) >= 3:
                category = parts[0].strip()
                word = parts[1].strip()
                count = int(parts[2].strip())
            elif len(parts) == 2: # Legacy fallback if LLM messes up
                category = "Technology" # Default
                word = parts[0].strip()
                count = int(parts[1].strip())
            else:
                continue

            # Basic cleanup
            word = word.replace('"', '').replace("'", "")
            
            # 제외 키워드 (너무 일반적이거나 상위 개념)
            # LLM, AI, 인공지능과 이들의 모든 변형 (LLMs, LLM., AI., AI's 등)을 제거
            EXCLUDED_BASES = ['LLM', 'AI', '인공지능']
            
            # 단어 정규화 (구두점 제거 후 비교)
            word_normalized = re.sub(r'[^\w가-힣]', '', word).strip()
            
            # 제외 대상인지 확인
            should_exclude = False
            for excluded in EXCLUDED_BASES:
                # 대소문자 구분 없이 정확히 일치하거나, excluded로 시작하는 경우
                if word_normalized.upper() == excluded.upper() or word_normalized.upper().startswith(excluded.upper() + 'S'):
                    should_exclude = True
                    break
            
            if len(word) > 1 and not should_exclude:
                word_counts[word] = count
                word_to_category[word] = category
        except:
            continue
            
    # Fallback if LLM fails or returns nothing
    if not word_counts:
        print("[WordCloud] LLM returned empty or invalid data. Using fallback keyword extraction...")
        
        # Simple fallback: Extract keywords using regex patterns
        try:
            # Combine all text
            full_text = " ".join(collected_text[:150])
            
            # Extract Korean words (2+ characters) and English words (3+ characters)
            korean_words = re.findall(r'[가-힣]{2,}', full_text)
            english_words = re.findall(r'[A-Z][a-zA-Z]{2,}', full_text)  # Capitalized words
            
            all_words = korean_words + english_words
            word_freq = Counter(all_words)
            
            # Extensive exclusion list
            EXCLUDED_WORDS = {
                'AI', 'LLM', '인공지능', 'ai', 'llm', 'Ai',
                # Common Korean particles and words
                '것', '등', '및', '이', '그', '수', '더', '때', '년', '월', '일', '시', '분',
                '기', '개', '곳', '명', '원', '위', '대', '중', '내', '외', '가지', '번째',
                '통해', '위해', '다', '제', '점', '매', '전', '후', '간', '만', '여', '약',
                '오늘', '내일', '어제', '올해', '금년', '내년', '작년', '모레', '그제',
                '최근', '현재', '당시', '이번', '다음', '지난', '올', '작', '내', '금',
                '우리', '저희', '여러', '각','모든', '많은', '적은', '큰', '작은',
                '있는', '없는', '되는', '하는', '말', '따른', '대한', '관련', '같은',
                '기사', '뉴스', '소식', '발표', '공개', '출시', '이용', '사용', '서비스',
                '관계자', '업계', '시장', '분야', '부문', '측', '그동안', '앞으로', '이후',
                '이상', '이하', '정도', '까지', '부터', '마다', '조', '억', '만',
                # Common English words
                'The', 'And', 'For', 'With', 'From', 'That', 'This', 'More', 'New',
                'All', 'How', 'Why', 'What', 'When', 'Where', 'Who', 'Which',
                'News', 'Today', 'New', 'About', 'After', 'Before', 'Now', 'Later',
            }
            
            # Known tech companies and important keywords (these should be KEPT)
            IMPORTANT_KEYWORDS = {
                'OpenAI', 'Google', 'Microsoft', 'Apple', 'Amazon', 'Meta', 'Tesla',
                'NVIDIA', 'Samsung', 'LG', 'ChatGPT', 'Gemini', 'Claude', '삼성', '엘지',
                '네이버', '카카오', '구글', '마이크로소프트', '애플', '아마존', '메타',
                '엔비디아', '테슬라', '바이트댄스', '알리바바', '텐센트',
            }
            
            # Filter and weight keywords
            for word, count in word_freq.most_common(100):
                # Skip single character words
                if len(word) < 2:
                    continue
                
                # Clean the word
                word_clean = word.strip()
                
                # Check if it's in important keywords (case-insensitive)
                is_important = any(word_clean.lower() == imp.lower() for imp in IMPORTANT_KEYWORDS)
                
                # Skip excluded words (unless it's important)
                if not is_important:
                    if word_clean in EXCLUDED_WORDS or word_clean.upper() in EXCLUDED_WORDS:
                        continue
                    
                    # Check base exclusions (AI, LLM, etc.)
                    should_exclude = False
                    for excluded in ['LLM', 'AI', '인공지능']:
                        word_upper = word_clean.upper()
                        if word_upper == excluded or word_upper.startswith(excluded + 'S'):
                            should_exclude = True
                            break
                    
                    if should_exclude:
                        continue
                
                # Assign weight based on frequency (cap at 10, boost important keywords)
                weight = min(count, 10)
                if is_important:
                    weight = min(weight + 3, 10)  # Boost important keywords
                
                word_counts[word_clean] = weight
                word_to_category[word_clean] = "Technology"  # Default category
                
                # Stop when we have enough keywords
                if len(word_counts) >= 50:
                    break
                    
            print(f"[WordCloud] Extracted {len(word_counts)} keywords using fallback method")
                    
        except Exception as e:
            print(f"[WordCloud] Fallback extraction failed: {e}")
            import traceback
            traceback.print_exc()

    return word_counts, word_to_category

def create_wordcloud_image(word_counts, word_to_category, output_path, font_path=None):
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
            
    # Define colors
    # Orange, Blue, Green, Purple
    CATEGORY_COLORS = {
        "Person": "#FF9F40", # Orange
        "People": "#FF9F40",
        "Company": "#36A2EB", # Blue
        "Technology": "#4BC0C0", # Green
        "Concept": "#4BC0C0",
        "Solution": "#9966FF", # Purple
        "Product": "#9966FF",
        "Institution": "#36A2EB" # Treat like company
    }
    DEFAULT_COLOR = "#999999"

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        category = word_to_category.get(word, "Technology")
        # Handle cases where category might be fuzzy
        for key, color in CATEGORY_COLORS.items():
            if key.lower() in category.lower():
                return color
        return DEFAULT_COLOR

    try:
        wc = WordCloud(
            font_path=font_path,
            width=1200,
            height=400,
            background_color='white',
            max_words=100,
            stopwords=None, # Already filtered
            color_func=color_func
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
