
import os
import re
import datetime
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

# Setup Jinja2 Environment
env = Environment(loader=FileSystemLoader("templates"))
template = env.get_template("quickview_page.html")

quickview_dir = "docs/quickview"
base_url = "https://vaax-maker.github.io/ai-news-daily/quickview"

if not os.path.exists(quickview_dir):
    print("Quickview directory not found.")
    exit()

files = [f for f in os.listdir(quickview_dir) if f.endswith(".html") and f != "index.html"]
print(f"Found {len(files)} Quickview pages to rebuild.")

for filename in files:
    path = os.path.join(quickview_dir, filename)
    print(f"Processing {filename}...")
    
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    
    # Extract Title
    title_el = soup.select_one(".quickview-title")
    title = title_el.get_text(strip=True) if title_el else "제목 없음"
    
    # Extract Date Display
    meta_el = soup.select_one(".quickview-meta")
    created_display = meta_el.get_text(strip=True).replace("📅", "").strip() if meta_el else ""
    
    # Extract Created Timestamp (for meta)
    created_at = ""
    meta_ts = soup.select_one("meta[name='created-at']")
    if meta_ts and meta_ts.get("content"):
        created_at = meta_ts.get("content")
    
    # Extract Content
    # Check for existing Shadow DOM structure first
    raw_template = soup.select_one("template#quickview-raw-content")
    if raw_template:
        print(f"  Existing Shadow DOM detected in {filename}. Extracting content from template.")
        content_html = raw_template.decode_contents()
    else:
        # Fallback to old structure
        content_div = soup.select_one("#quickview-body-content")
        if content_div:
            content_html = content_div.decode_contents()
        else:
            # Last resort: try to find .quickview-body class if ID is missing
            body_div = soup.select_one(".quickview-body")
            if body_div:
                content_html = body_div.decode_contents()
            else:
                print(f"  Warning: No content container found in {filename}. Skipping.")
                continue

    # Prepare Context
    page_url = f"{base_url}/{filename}"
    
    # Re-render
    new_html = template.render(
        title=title,
        created_display=created_display,
        created_at=created_at,
        content=content_html,
        page_url=page_url
    )
    
    # Overwrite
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)

print("Done rebuilding Quickview pages.")
