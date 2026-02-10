
import os
import re
from bs4 import BeautifulSoup

def fix_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 1. Regex Cleanup of any remaining ** (Safety net)
        if "**" in content:
             content = re.sub(r"\*\*", "", content)
        
        soup = BeautifulSoup(content, 'html.parser')
        modified = False
        
        # Find all summary lists
        summary_lists = soup.find_all('ul', class_='summary-list')
        
        for ul in summary_lists:
            # Get first li
            li = ul.find('li')
            if not li:
                continue
                
            contents = li.contents
            if not contents:
                continue
                
            first_item = contents[0]
            
            # Check if already highlighted
            if first_item.name == 'span' and 'highlight' in first_item.get('class', []):
                continue
            
            # If text node
            if isinstance(first_item, str):
                text = str(first_item)
                subject = None
                separator = ""
                
                # Pattern 1: Colon
                colon_match = re.match(r"^([^:]+):", text)
                if colon_match and len(colon_match.group(1)) < 30:
                    subject = colon_match.group(1)
                    separator = ":"
                else:
                    # Pattern 2: Comma
                    comma_match = re.match(r"^([^,]+),", text)
                    if comma_match and len(comma_match.group(1)) < 30:
                        subject = comma_match.group(1)
                        separator = ","
                
                if subject:
                    # Create span
                    new_span = soup.new_tag("span", attrs={"class": "highlight"})
                    new_span.string = subject
                    
                    # Replace text node with span + separator + rest
                    # We need to split the text node?
                    # Actually, easier to replace the text node with multiple nodes?
                    # BeautifulSoup makes this tricky.
                    # Let's replace the whole li content if it's simple?
                    
                    # Simplified approach: Just replace the text of the first item
                    # But first item is the text node itself.
                    # We want: <span>Subject</span>: Rest
                    
                    rest_of_text = text[len(subject):] 
                    # If separator matches part of text
                    # Actually colon_match includes colon? No, group(1) excludes colon.
                    # So text = subject + rest_of_text
                    
                    first_item.replace_with(new_span)
                    if rest_of_text:
                        new_span.insert_after(rest_of_text)
                    
                    modified = True
                    # print(f"  [Highlight] {file_path}: Processed '{subject}'")

        if modified:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            print(f"  [SAVED] {file_path}")
            return 1
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return 0

if __name__ == "__main__":
    count = 0
    for root, _, files in os.walk("docs/"):
        for file in files:
            if file.endswith(".html"):
                count += fix_file(os.path.join(root, file))
    print(f"Total files updated: {count}")
