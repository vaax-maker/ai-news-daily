
import os
import re

def fix_bold_in_html(content: str, filename: str) -> str:
    replacements = 0
    new_content = content
    
    if "**" not in content:
        return content, 0

    def _wrap_highlight(text):
        return f"<span class='highlight'>{text}</span>"
        
    # 1. Standard bold with potential newlines/tags 
    pattern_std = r"\*\*(.+?)\*\*"
    
    def replacement(match):
        return _wrap_highlight(match.group(1))

    new_content, count = re.subn(pattern_std, replacement, new_content, flags=re.DOTALL)
    if count > 0:
        print(f"  [FIX] {filename}: Replaced standard bold pair {count} times.")
    replacements += count
    
    # 2. Handle cases where closing ** is missing but it's a list item header or start of line
    # e.g. <li>**Subject: content</li>
    # Match **Text... until : or < or newline
    pattern_open_only = r"(<li>\s*)\*\*(.+?)(:| <)" 
    
    def replacement_open(match):
        # careful not to match too much
        # pattern captures group 1 (<li>), group 2 (text), group 3 (terminator)
        # We need to refine pattern to stop at : or <
        # Let's use a simpler approach: 
        # Find <li>**...
        return match.group(0) # Placeholder

    # Actually, let's use the logic I viewed in Step 393:
    # pattern_open_only = r"(<li>\\s*)\\*\\*(.+?)(:)" 
    
    pattern_open_only_corrected = r"(<li>\s*)\*\*(.+?)(:)"
    
    def replacement_open_corrected(match):
        # careful not to match too much
        if len(match.group(2)) < 50:
             return f"{match.group(1)}{_wrap_highlight(match.group(2))}{match.group(3)}"
        return match.group(0)
        
    new_content, count2 = re.subn(pattern_open_only_corrected, replacement_open_corrected, new_content, flags=re.DOTALL | re.IGNORECASE)
    if count2 > 0:
         print(f"  [FIX] {filename}: Replaced open-only bold {count2} times.")
    replacements += count2
    
    # 3. Clean up ALL remaining **
    if "**" in new_content:
        cleaned_content, count3 = re.subn(r"\*\*", "", new_content)
        if count3 > 0:
            print(f"  [CLEANUP] {filename}: Removed {count3} remaining '**' artifacts.")
        replacements += count3
        new_content = cleaned_content

    return new_content, replacements

def process_directory(directory: str):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    new_content, count = fix_bold_in_html(content, file)
                    
                    if count > 0:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(new_content)
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")

if __name__ == "__main__":
    process_directory("docs/")
