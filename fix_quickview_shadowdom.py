#!/usr/bin/env python3
"""
Fix Quickview Shadow DOM Issue
- Remove Shadow DOM wrapper from all quickview pages
- Replace with direct content injection + CSS overrides
"""

import os
import re
from pathlib import Path

QUICKVIEW_DIR = Path(__file__).parent / "docs" / "quickview"


def fix_quickview_file(filepath: Path) -> bool:
    """Fix a single quickview HTML file by removing Shadow DOM."""
    
    content = filepath.read_text(encoding='utf-8')
    
    # Check if this file uses Shadow DOM
    if 'attachShadow' not in content:
        print(f"  ⏭ {filepath.name}: No Shadow DOM found")
        return False
    
    # Pattern to match the Shadow DOM section
    # From: <!-- Raw content container (hidden) --> ... </script>
    # To: <!-- Direct content injection --> <div class="quickview-body">{{ content }}</div>
    
    # Extract the raw content from template
    template_pattern = r'<template id="quickview-raw-content">\s*(.*?)\s*</template>'
    template_match = re.search(template_pattern, content, re.DOTALL)
    
    if not template_match:
        print(f"  ⚠ {filepath.name}: Could not find template content")
        return False
    
    raw_content = template_match.group(1).strip()
    
    # Pattern to match the entire Shadow DOM block
    shadow_block_pattern = r'<!-- Raw content container \(hidden\) -->.*?</script>'
    
    # Alternative pattern if the comment is different
    if not re.search(shadow_block_pattern, content, re.DOTALL):
        shadow_block_pattern = r'<template id="quickview-raw-content">.*?</script>'
    
    # Create the replacement - direct injection with class
    replacement = f'''<!-- Direct content injection (no Shadow DOM for external script compatibility) -->
    <div class="quickview-body">
        {raw_content}
    </div>'''
    
    # Replace the Shadow DOM block
    new_content = re.sub(shadow_block_pattern, replacement, content, flags=re.DOTALL)
    
    # Also remove the Shadow Wrapper div if it exists separately
    new_content = re.sub(r'\s*<!-- Shadow Wrapper -->\s*<div id="quickview-shadow-host"></div>\s*', '', new_content)
    
    # Add CSS overrides if not already present
    if '.quickview-body > h1' not in new_content:
        css_overrides = '''
    /* === CSS OVERRIDES (replacing Shadow DOM isolation) === */
    /* Hide duplicate titles from injected content */
    .quickview-body > h1,
    .quickview-body > .container > h1,
    .quickview-body > body > .container > h1 {
        display: none !important;
    }

    /* Flatten Container/Card styles from injected content */
    .quickview-body .container,
    .quickview-body .summary-box {
        box-shadow: none !important;
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        border-radius: 0 !important;
    }

    /* Hide internal footer/meta from injected content */
    .quickview-body > footer,
    .quickview-body .container > footer,
    .quickview-body .meta-date,
    .quickview-body .meta-info {
        display: none !important;
    }

    /* Adjust heading styles inside quickview */
    .quickview-body h2 {
        font-size: 1.4rem;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        color: #333;
    }

    .quickview-body h3 {
        font-size: 1.15rem;
        margin-top: 1.2rem;
        color: #444;
    }

    /* Tags in injected content */
    .quickview-body .tag {
        display: inline-block;
        background-color: #475569;
        color: white;
        padding: 4px 10px;
        border-radius: 15px;
        font-size: 0.8rem;
        margin-right: 6px;
        margin-top: 6px;
    }

    /* Neutralize global body styles that might leak from injected content */
    .quickview-body body {
        all: unset;
        display: block;
    }
'''
        # Insert before </style> in the quickview-specific styles
        # Find the last </style> before </head>
        style_end_pattern = r'(\.quickview-body pre \{[^}]+\})\s*(\/\* === MOBILE RESPONSIVE ===)'
        if re.search(style_end_pattern, new_content):
            new_content = re.sub(style_end_pattern, f'\\1\n{css_overrides}\n    \\2', new_content)
        else:
            # Fallback: insert before /* === MOBILE RESPONSIVE ===
            mobile_pattern = r'(\s*)(\/\* === MOBILE RESPONSIVE ===)'
            new_content = re.sub(mobile_pattern, f'{css_overrides}\n\\1\\2', new_content)
    
    # Write back
    filepath.write_text(new_content, encoding='utf-8')
    print(f"  ✅ {filepath.name}: Fixed!")
    return True


def main():
    print("🔧 Fixing Quickview Shadow DOM issues...\n")
    
    if not QUICKVIEW_DIR.exists():
        print(f"❌ Directory not found: {QUICKVIEW_DIR}")
        return
    
    html_files = list(QUICKVIEW_DIR.glob("*.html"))
    if not html_files:
        print("❌ No HTML files found")
        return
    
    print(f"Found {len(html_files)} HTML files\n")
    
    fixed_count = 0
    for filepath in sorted(html_files):
        if filepath.name == 'index.html':
            continue  # Skip index
        if fix_quickview_file(filepath):
            fixed_count += 1
    
    print(f"\n✨ Done! Fixed {fixed_count} files.")


if __name__ == "__main__":
    main()
