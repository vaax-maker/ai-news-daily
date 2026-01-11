
import os
import re

quickview_dir = "docs/quickview"
if not os.path.exists(quickview_dir):
    print("Quickview directory not found.")
    exit()

files = [f for f in os.listdir(quickview_dir) if f.endswith(".html")]
print(f"Scanning {len(files)} files in {quickview_dir}...")

# Regex to find: ="[url](url)" pattern
# We are looking for something like: src="[https://...](https://...)"
# The group 1 will be the actual URL inside the parentheses.
pattern = re.compile(r'="\[(.*?)]\((.*?)\)"')

# Also handle cases where it might be single quoted, though less likely in this codebase
pattern_single = re.compile(r"='\[(.*?)]\((.*?)\)'")

count_fixed = 0

for filename in files:
    path = os.path.join(quickview_dir, filename)
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    
    # Replace double quoted
    # Replacement: ="\2" (using the second group which is the url in parens, or first group since they are usually same)
    # Let's use the one in parentheses to be safe, which is group 2.
    new_content = pattern.sub(r'="\2"', new_content)
    
    # Replace single quoted
    new_content = pattern_single.sub(r"='\2'", new_content)
    
    if content != new_content:
        print(f"Fixing malformed links in {filename}...")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        count_fixed += 1

print(f"Done. Fixed {count_fixed} files.")
