#!/usr/bin/env python3
"""
Fix h1 line-height in all webshare HTML files to prevent overlapping Korean titles.
Adds or updates line-height property in h1 CSS rules.
"""

import os
import re
import glob

WEBSHARE_DIR = "/Users/fovea/Documents/vsc-codex/VAAXfinal/docs/webshare"

def fix_h1_line_height(filepath):
    """Add line-height: 1.4 to h1 CSS rules if not present or update existing."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Pattern 1: h1 { ... } without line-height
    # Find h1 CSS rule and add line-height if not present
    h1_pattern = r'(h1\s*\{[^}]*?)(font-size[^;]*;)([^}]*\})'
    
    def add_line_height(match):
        before = match.group(1)
        font_size = match.group(2)
        after = match.group(3)
        full_rule = before + font_size + after
        
        # Check if line-height already exists
        if 'line-height' in full_rule:
            # Update existing line-height if it's less than 1.4
            return re.sub(r'line-height:\s*[0-9.]+;?', 'line-height: 1.4;', full_rule)
        else:
            # Add line-height after font-size
            return before + font_size + ' line-height: 1.4;' + after
    
    content = re.sub(h1_pattern, add_line_height, content)
    
    # Also handle cases where h1 rule might not have font-size first
    # Pattern 2: General h1 { ... } - add line-height if completely missing
    if 'h1 {' in content or 'h1{' in content:
        # Another pattern match for h1 without line-height
        def add_if_missing(match):
            rule = match.group(0)
            if 'line-height' not in rule:
                # Insert line-height after the opening brace
                return re.sub(r'(h1\s*\{)', r'\1 line-height: 1.4;', rule)
            return rule
        content = re.sub(r'h1\s*\{[^}]+\}', add_if_missing, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Fixed: {os.path.basename(filepath)}")
        return True
    else:
        print(f"⏭️ Skipped (no change needed): {os.path.basename(filepath)}")
        return False

def main():
    html_files = glob.glob(os.path.join(WEBSHARE_DIR, "*.html"))
    
    fixed_count = 0
    for filepath in html_files:
        # Skip the list page
        if 'secret_list' in filepath:
            continue
        try:
            if fix_h1_line_height(filepath):
                fixed_count += 1
        except Exception as e:
            print(f"❌ Error processing {filepath}: {e}")
    
    print(f"\n📊 Total files fixed: {fixed_count}")

if __name__ == "__main__":
    main()
