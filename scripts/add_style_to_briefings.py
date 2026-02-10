
import os

CSS_TO_INJECT = """
        /* Custom Highlight */
        .highlight {
            background-color: #d9f99d;
            padding: 0px 4px;
            border-radius: 4px;
            font-weight: 700;
        }
"""

def fix_briefing_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if ".highlight {" in content:
            print(f"Skipping {file_path} (already has highlight style)")
            return 0
            
        if "</style>" not in content:
            print(f"Skipping {file_path} (no style block found)")
            return 0
            
        # Inject before </style>
        new_content = content.replace("</style>", CSS_TO_INJECT + "\n    </style>")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        print(f"Fixed {file_path}")
        return 1
        
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
