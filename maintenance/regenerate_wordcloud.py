#!/usr/bin/env python3
"""
Script to regenerate word cloud only
"""
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print(f"[WordCloud] Loaded .env file. GEMINI_API_KEY: {'set' if os.getenv('GEMINI_API_KEY') else 'not set'}")
except ImportError:
    print("[WordCloud] Warning: python-dotenv not installed, using system environment variables")

from src.utils.wordcloud_generator import extract_weekly_keywords, create_wordcloud_image

def main():
    print("[WordCloud] Starting word cloud regeneration...")
    
    try:
        # Extract keywords from last 7 days
        wc_counts, wc_categories = extract_weekly_keywords(docs_dir="docs", days=2)
        
        # Set output path
        wc_output_path = "static/images/weekly_wordcloud.png"
        os.makedirs(os.path.dirname(wc_output_path), exist_ok=True)
        
        # Create word cloud image
        create_wordcloud_image(wc_counts, wc_categories, wc_output_path)
        
        # Also copy to docs/static for deployment
        docs_output_path = "docs/static/images/weekly_wordcloud.png"
        os.makedirs(os.path.dirname(docs_output_path), exist_ok=True)
        
        import shutil
        shutil.copy(wc_output_path, docs_output_path)
        
        print(f"[WordCloud] Successfully generated:")
        print(f"  - {wc_output_path}")
        print(f"  - {docs_output_path}")
        print(f"[WordCloud] Total keywords: {len(wc_counts)}")
        
    except Exception as e:
        print(f"[WordCloud] Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
