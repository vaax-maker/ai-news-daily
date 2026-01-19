#!/usr/bin/env python3
"""
Fix nested HTML structure in existing quickview files.
Extracts only the user content from quickview-body, removing any nested DOCTYPE/html/head/body.
"""

import os
import re
from pathlib import Path
from bs4 import BeautifulSoup

QUICKVIEW_DIR = Path(__file__).parent / "docs" / "quickview"

def extract_body_content(html_content: str) -> str:
    """Extract body content from a full HTML document."""
    # If it doesn't contain DOCTYPE or html tags, it's already clean
    if '<!DOCTYPE' not in html_content and '<html' not in html_content:
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract styles from head (if any)
    styles = []
    head = soup.find('head')
    if head:
        for style in head.find_all('style'):
            styles.append(str(style))
    
    # Get body content
    body = soup.find('body')
    if body:
        body_content = ''.join(str(child) for child in body.children)
        return '\n'.join(styles) + '\n' + body_content if styles else body_content
    
    return html_content

def fix_quickview_file(filepath: Path) -> bool:
    """Fix a single quickview HTML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the full quickview page
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find quickview-body div
        quickview_body = soup.find('div', class_='quickview-body')
        if not quickview_body:
            print(f"  ⏭️  No quickview-body found: {filepath.name}")
            return False
        
        # Check if there's a nested DOCTYPE or html tag inside
        body_content = str(quickview_body)
        if '<!DOCTYPE' not in body_content and '<html' not in body_content:
            print(f"  ✅ Already clean: {filepath.name}")
            return False
        
        # Extract the nested HTML content
        inner_html = quickview_body.decode_contents()
        
        # Parse the nested HTML to extract body content
        cleaned_content = extract_body_content(inner_html)
        
        # Replace quickview-body content
        quickview_body.clear()
        new_content = BeautifulSoup(cleaned_content, 'html.parser')
        for child in list(new_content.children):
            quickview_body.append(child)
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        print(f"  🔧 Fixed: {filepath.name}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error processing {filepath.name}: {e}")
        return False

def main():
    print("=" * 60)
    print("🔧 Quickview HTML Structure Fixer")
    print("=" * 60)
    print(f"Directory: {QUICKVIEW_DIR}")
    print("")
    
    if not QUICKVIEW_DIR.exists():
        print("❌ Quickview directory not found!")
        return
    
    html_files = list(QUICKVIEW_DIR.glob("*.html"))
    html_files = [f for f in html_files if f.name != "index.html"]  # Skip index
    
    print(f"Found {len(html_files)} quickview files to check...\n")
    
    fixed_count = 0
    for filepath in sorted(html_files):
        if fix_quickview_file(filepath):
            fixed_count += 1
    
    print("")
    print("=" * 60)
    print(f"✅ Done! Fixed {fixed_count} files.")
    print("=" * 60)

if __name__ == "__main__":
    main()
