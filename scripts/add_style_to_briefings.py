
import os
import re

CSS_TO_INJECT = """
        /* Custom Highlight */
        .highlight {
            background-color: #e5f7da;
            color: #111827;
            padding: 2px 4px;
            border-radius: 4px;
            font-weight: 400;
        }
"""

def fix_briefing_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # If it has old highlight style, replace it
        # We look for the block start and end.
        # But easier to just use regex to replace the whole .highlight {...} block if present
        
        # Or, since we know exactly what we injected last time:
        old_style_start = ".highlight {"
        if old_style_start in content:
            # Simple replace of the block might be tricky due to formatting.
            # Let's use regex to find .highlight { ... }
            pattern = r"\.highlight\s*\{[^}]+\}"
            new_style_block = CSS_TO_INJECT.strip()
            
            new_content, count = re.subn(pattern, new_style_block, content)
            if count > 0:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated style in {file_path}")
                return 1
            
        # If not present, inject it (fallback)
        if "</style>" in content and ".highlight" not in content:
             new_content = content.replace("</style>", CSS_TO_INJECT + "\n    </style>")
             with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
             print(f"Injected style into {file_path}")
             return 1
            
        print(f"No changes needed for {file_path}")
        return 0
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

if __name__ == "__main__":
    count = 0
    
    # Fix main briefing file
    if os.path.exists("docs/briefing.html"):
        count += fix_briefing_file("docs/briefing.html")
        
    # Fix archived briefings
    briefing_dir = "docs/briefing"
    if os.path.exists(briefing_dir):
        for filename in os.listdir(briefing_dir):
            if filename.endswith(".html"):
                count += fix_briefing_file(os.path.join(briefing_dir, filename))
                
    print(f"Total briefing files updated: {count}")
