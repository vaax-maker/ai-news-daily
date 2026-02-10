
import os
import re

def remove_inline_styles(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Regex to find <span class='highlight' style='...'> and replace with <span class='highlight'>
        # Pattern handles optional whitespace
        # We capture the content inside the span to preserve it
        pattern = r"<span class=['\"]highlight['\"]\s+style=['\"][^'\"]*['\"]>(.*?)</span>"
        
        def replacement(match):
            return f"<span class='highlight'>{match.group(1)}</span>"
            
        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        
        if count > 0:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Fixed {count} inline styles in {file_path}")
            return count
            
        return 0
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

if __name__ == "__main__":
    total_cleaned = 0
    
    # Target specific directories
    dirs_to_clean = ["docs", "docs/briefing", "docs/ai", "docs/xr", "docs/ai/daily", "docs/xr/daily"]
    
    for d in dirs_to_clean:
        if os.path.exists(d):
            for filename in os.listdir(d):
                if filename.endswith(".html"):
                    total_cleaned += remove_inline_styles(os.path.join(d, filename))
                    
    print(f"Total inline styles removed: {total_cleaned}")
