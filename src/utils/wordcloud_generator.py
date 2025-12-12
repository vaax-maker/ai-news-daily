import os
import glob
from datetime import datetime, timedelta
from collections import Counter
import re
from wordcloud import WordCloud
from bs4 import BeautifulSoup

def extract_weekly_keywords(docs_dir="docs", days=7):
    """
    Extracts keywords from AI and XR daily summaries for the past `days` days.
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    text_content = ""

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
                        
                        # Extract text from headings and paragraphs
                        # Adjust selectors based on actual HTML structure if needed
                        # Usually h3 are titles in these generate files
                        for tag in soup.find_all(['h3', 'p', 'li']):
                            text_content += tag.get_text() + " "
                    
                    files_processed += 1
            except ValueError:
                continue # Skip files that don't match date format

    print(f"Processed {files_processed} files for word cloud.")
    
    # Basic tokenization and cleaning
    # Remove special chars but keep Korean and English
    # Simple regex to keep alphanumeric and spaces
    # This might need refinement for Korean efficiency but works for a start
    
    # Use a simple split for now. 
    # For better Korean processing, Konlpy is great but trying to avoid extra bulky deps if simple works.
    # Let's clean up punctuation.
    
    # Remove url like strings
    text_content = re.sub(r'http\S+', '', text_content)
    
    # Extract words (Hangul and English)
    words = re.findall(r'[a-zA-Z0-9가-힣]+', text_content)
    
    # Filter stopwords (very basic list)
    stopwords = {'이', '그', '저', '것', '수', '등', '를', '을', '의', '가', '이', '은', '는', '에', '와', '과', '한', '하다', '있다', '되다', 'to', 'and', 'of', 'the', 'in', 'a', 'for', 'on'}
    filtered_words = [w for w in words if w not in stopwords and len(w) > 1]
    
    word_counts = Counter(filtered_words)
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
            width=800,
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
