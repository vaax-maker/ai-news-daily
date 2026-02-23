import re
import os
import sys

# Add project root to sys.path to allow importing src
sys.path.append(os.getcwd())

from src.utils.common import HIGHLIGHT_COLOR

def test_highlight_color_constant():
    """Verify HIGHLIGHT_COLOR in common.py is #e5f7da"""
    assert HIGHLIGHT_COLOR.lower() == "#e5f7da", \
        f"Expected HIGHLIGHT_COLOR to be #e5f7da, but got {HIGHLIGHT_COLOR}"

def test_css_highlight_color():
    """Verify .highlight background-color in CSS files is #e5f7da"""
    css_files = [
        "static/css/style.css",
        "docs/static/css/style.css"
    ]
    
    # Regex to find .highlight { ... background-color: #...... ... }
    # Simplified check: verify .highlight rule contains background-color: #e5f7da
    
    for css_path in css_files:
        if not os.path.exists(css_path):
            continue
            
        with open(css_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find .highlight block
        # This is a simple regex and might need adjustment if CSS format changes drastically
        match = re.search(r'\.highlight\s*{([^}]+)}', content)
        assert match, f".highlight class not found in {css_path}"
        
        block_content = match.group(1)
        
        # Check background-color
        bg_match = re.search(r'background-color:\s*(#[a-fA-F0-9]{6})', block_content)
        assert bg_match, f"background-color not found in .highlight of {css_path}"
        
        color = bg_match.group(1).lower()
        assert color == "#e5f7da", \
            f"Expected .highlight background-color to be #e5f7da in {css_path}, but got {color}"

if __name__ == "__main__":
    try:
        test_highlight_color_constant()
        print("PASS: HIGHLIGHT_COLOR constant")
        test_css_highlight_color()
        print("PASS: CSS highlight color")
        print("ALL TESTS PASSED")
    except AssertionError as e:
        print(f"FAIL: {e}")
        exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
