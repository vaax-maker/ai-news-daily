
import os
import re
from bs4 import BeautifulSoup

DOCS_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs'

def clean_bullets(text):
    # Remove specific unicode bullets and starting dashes
    text = re.sub(r'^[ \t]*[▪▫❑•\-]+[ \t]*', '', text)
    text = re.sub(r'<li>\s*[▪▫❑•\-]+\s*', '<li>', text)
    return text

def process_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    soup = BeautifulSoup(content, 'html.parser')
    changed = False
    
    # 1. Clean residual bullets in existing lists
    for li in soup.find_all('li'):
        original_text = li.decode_contents()
        cleaned_text = clean_bullets(original_text)
        if original_text != cleaned_text:
            li.string = cleaned_text # This might lose inner tags, but usually these are raw text. 
            # If inner tags exist (like start <span>), we need to be careful.
            # Using simple regex on the string content is safer if we iterate children.
            pass # Actually, simple regex on full html content is potentially risky for tags.
            # Let's stick to the text replacement at string level for the whole file at the end involving the bullets.

    # 2. Find and Split Mashed Articles
    # Strategy: Find news-item that contains the "mashed" pattern.
    # The mashed pattern is in <li>...----------------...</li>
    
    # We will look for <article class="news-item"> that contains a <ul> with such an <li>.
    
    articles = soup.find_all('article', class_='news-item')
    
    new_articles = [] # Store tuple of (reference_article, [new_article_soup_objects]) to insert after
    
    for article in articles:
        summary_div = article.find('div', class_='news-summary')
        if not summary_div: continue
        
        ul = summary_div.find('ul', class_='summary-list')
        if not ul: continue
        
        items_to_remove = []
        splittable_found = False
        
        # We need to iterate over li's. If an li contains '----------------', it is a header for a NEW article.
        # But wait, looking at the file:
        # <li>DeepBrain AI...----------------...</li>
        # This WHOLE li is actually the Title + Summary of a new article.
        
        mashed_items = []
        
        for li in ul.find_all('li'):
            text = li.get_text()
            if '----------------' in text:
                splittable_found = True
                mashed_items.append(li)
        
        if splittable_found:
            changed = True
            # For each mashed item, create a NEW article block
            for li in mashed_items:
                text = li.get_text()
                # Split Title and Summary
                parts = text.split('----------------')
                title_text = parts[0].strip()
                summary_text = parts[1].strip() if len(parts) > 1 else ""
                
                # Check for "날짜...원문" at the end of summary
                date_match = re.search(r'날짜(\d{4}\.\d{2}\.\d{2})원문', summary_text)
                pub_date = date_match.group(1) if date_match else "Unknown Date"
                # Remove the date string from summary
                summary_text = re.sub(r'날짜\d{4}\.\d{2}\.\d{2}원문', '', summary_text).strip()
                
                # Create new article structure
                new_art = soup.new_tag('article', attrs={'class': 'news-item'})
                
                # Header
                header = soup.new_tag('div', attrs={'class': 'news-header'})
                h2 = soup.new_tag('h2', attrs={'class': 'news-title'})
                a_link = soup.new_tag('a', href='#', target='_blank') # No link available
                a_link.string = title_text
                h2.append(a_link)
                
                meta = soup.new_tag('div', attrs={'class': 'news-meta'})
                meta.string = f"Extracted | {pub_date.replace('.', '')}"
                
                header.append(h2)
                header.append(meta)
                new_art.append(header)
                
                # Body
                body = soup.new_tag('div', attrs={'class': 'news-body'})
                sum_div = soup.new_tag('div', attrs={'class': 'news-summary'})
                
                # Summary might need bullets if it had bullet characters in text
                # Ideally wrap in ul/li?
                # The text usually starts with ❑ or ▪︎. Let's make it a clean list.
                desc_ul = soup.new_tag('ul', attrs={'class': 'summary-list'})
                
                # Split summary by bullets?
                bullet_parts = re.split(r'[▪▫❑•]', summary_text)
                for part in bullet_parts:
                    p = part.strip()
                    if p:
                        new_li = soup.new_tag('li')
                        new_li.string = p
                        desc_ul.append(new_li)
                        
                sum_div.append(desc_ul)
                body.append(sum_div)
                new_art.append(body)
                
                new_articles.append((article, new_art))
                
                # Remove this li from the ORIGINAL article
                li.decompose()

    # Insert new articles after the original one
    for ref_art, new_art in new_articles:
        ref_art.insert_after(new_art)

    if changed:
        # Also run global regex for bullet cleanup on the whole string as a final pass
        final_html = str(soup)
        final_html = clean_bullets(final_html)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)
        print(f"Fixed mashed content in: {filepath}")
        return True
    
    # Even if no mashed content, run bullet cleanup
    original_str = str(soup)
    cleaned_str = clean_bullets(original_str)
    if original_str != cleaned_str:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_str)
        print(f"Cleaned bullets in: {filepath}")
        return True

    return False

def main():
    for root, dirs, files in os.walk(DOCS_DIR):
        for file in files:
            if file.endswith('.html') and 'daily' in root:
                process_file(os.path.join(root, file))

if __name__ == '__main__':
    main()
