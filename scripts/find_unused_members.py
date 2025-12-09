
import os
import sys
import re

def main():
    # Paths
    base_dir = r"c:\Users\mrbadguy\Documents\mycode\ai-news-daily"
    config_path = os.path.join(base_dir, "config", "members.yaml")
    data_dir = os.path.join(base_dir, "data", "members")
    docs_dir = os.path.join(base_dir, "docs", "members")

    # 1. Load Config (Manual Parse)
    active_members = set()
    in_members_block = False
    
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip()
            if stripped == "members:":
                in_members_block = True
                continue
            
            if in_members_block:
                # Check indentation
                if not line.startswith("  "):
                    # End of block if not indented (and not empty)
                    if stripped and not line.startswith(" "):
                        in_members_block = False
                        continue
                
                # Check for key (2 spaces + key + :)
                # e.g. "  MemberName:"
                match = re.match(r"^  ([^ :]+):", line)
                if match:
                    key = match.group(1)
                    active_members.add(key)
                # Handle quoted keys if any? YAML allows "Key":
                match_quoted = re.match(r"^  \"([^\"]+)\":", line)
                if match_quoted:
                    key = match_quoted.group(1)
                    active_members.add(key)
                    
    print(f"Active members count: {len(active_members)}")
    # Just to be sure we parsed correctly, print first 5
    # print(list(active_members)[:5])

    # 2. Check Data Dir
    print("\n--- Unused Data Files ---")
    if os.path.exists(data_dir):
        files = sorted(os.listdir(data_dir))
        for f in files:
            if not f.endswith(".json"): continue
            
            key_from_file = f.replace(".json", "")
            
            # Exact match check
            if key_from_file not in active_members:
                print(f"[DATA] {f}")

    # 3. Check Docs Dir
    print("\n--- Unused Docs Files ---")
    if os.path.exists(docs_dir):
        files = sorted(os.listdir(docs_dir))
        
        expected_docs = set()
        expected_docs.add("index.html")
        expected_docs.add("daily") 
        
        for m in active_members:
            safe = m.replace("/", "_").replace("\\", "_")
            expected_docs.add(f"{safe}.html")
            
        for f in files:
            if not f.endswith(".html"): continue
            if f not in expected_docs:
                print(f"[DOCS] {f}")

if __name__ == "__main__":
    main()
