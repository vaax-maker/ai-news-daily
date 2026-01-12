#!/usr/bin/env python3
"""
Simple Flask server to trigger immediate message sending from admin panel.
Run this server locally: python3 admin_server.py
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import json
import re
import subprocess
from datetime import datetime
from html.parser import HTMLParser

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

# Set the service account path
os.environ["FIREBASE_SERVICE_ACCOUNT"] = os.path.join(
    PROJECT_ROOT,
    "vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json"
)

# Webshare configuration
WEBSHARE_DIR = os.path.join(PROJECT_ROOT, "docs", "webshare")
WEBSHARE_INDEX = os.path.join(WEBSHARE_DIR, "index.json")
WEBSHARE_BASE_URL = "https://vaax-maker.github.io/ai-news-daily/webshare"

app = Flask(__name__)
CORS(app)  # Enable CORS for admin panel access


class TitleExtractor(HTMLParser):
    """Extract title from HTML content."""
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True
    
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
    
    def handle_data(self, data):
        if self.in_title:
            self.title += data


def extract_title(html_content):
    """Extract title from HTML, return 'untitled' if not found."""
    parser = TitleExtractor()
    try:
        parser.feed(html_content)
        title = parser.title.strip()
        return title if title else None
    except:
        return None


def sanitize_filename(title):
    """Convert title to safe filename."""
    if not title:
        # Generate unique untitled name
        timestamp = datetime.now().strftime("%Y%m%d")
        random_suffix = os.urandom(3).hex()
        return f"untitled-{timestamp}-{random_suffix}"
    
    # Convert to lowercase and replace spaces with hyphens
    filename = title.lower().strip()
    filename = re.sub(r'\s+', '-', filename)
    # Remove special characters except hyphens and Korean
    filename = re.sub(r'[^\w\-\uAC00-\uD7A3]', '', filename)
    # Remove multiple hyphens
    filename = re.sub(r'-+', '-', filename)
    filename = filename.strip('-')
    
    return filename if filename else sanitize_filename(None)


def get_unique_filename(base_filename):
    """Ensure filename is unique by adding suffix if needed."""
    filename = base_filename
    counter = 2
    while os.path.exists(os.path.join(WEBSHARE_DIR, f"{filename}.html")):
        filename = f"{base_filename}-{counter}"
        counter += 1
    return filename


def load_webshare_index():
    """Load webshare index.json."""
    if os.path.exists(WEBSHARE_INDEX):
        try:
            with open(WEBSHARE_INDEX, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"pages": []}


def save_webshare_index(index_data):
    """Save webshare index.json."""
    with open(WEBSHARE_INDEX, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def git_push(message):
    """Execute git add, commit, pull --rebase, and push."""
    try:
        # 1. Add webshare files and .gitignore
        subprocess.run(["git", "add", "docs/webshare/", ".gitignore"], cwd=PROJECT_ROOT, check=True)
        
        # 2. Commit (may fail if nothing to commit, which is OK)
        result = subprocess.run(["git", "commit", "-m", message], cwd=PROJECT_ROOT, 
                               capture_output=True, text=True)
        
        commit_success = True
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                print("Nothing to commit, proceeding to push...")
                commit_success = False  # Nothing committed, but might need to push previous commits
            else:
                return False, f"Commit failed: {result.stderr}"
        
        # 3. Pull any remote changes (rebase)
        # This works even if we just committed, as it replays our commit on top of remote
        subprocess.run(["git", "pull", "--rebase"], cwd=PROJECT_ROOT, check=True, 
                      capture_output=True, timeout=60)
        
        # 4. Push
        subprocess.run(["git", "push"], cwd=PROJECT_ROOT, check=True, timeout=60)
        return True, "Git push successful"

    except subprocess.TimeoutExpired:
        return False, "Git operation timed out"
    except subprocess.CalledProcessError as e:
        # Try to capture stderr if available
        error_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
             error_msg += f": {e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else e.stderr}"
        return False, f"Git error: {error_msg}"


@app.route('/trigger-send', methods=['POST'])
def trigger_send():
    """Trigger immediate message sending."""
    try:
        from scripts.process_scheduled import main
        print("🚀 Processing pending notifications...")
        main()
        return jsonify({"success": True, "message": "Messages processed successfully!"})
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "running"})


@app.route('/webshare', methods=['POST'])
def create_webshare():
    """Create a new webshare page."""
    try:
        data = request.get_json()
        html_content = data.get('html', '').strip()
        
        if not html_content:
            return jsonify({"success": False, "message": "HTML content is required"}), 400
        
        # Extract title from HTML
        title = extract_title(html_content)
        display_title = title or "Untitled Page"
        
        # Generate safe filename
        base_filename = sanitize_filename(title)
        filename = get_unique_filename(base_filename)
        
        # Save HTML file
        filepath = os.path.join(WEBSHARE_DIR, f"{filename}.html")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Update index.json
        url = f"{WEBSHARE_BASE_URL}/{filename}.html"
        index_data = load_webshare_index()
        index_data["pages"].insert(0, {
            "filename": f"{filename}.html",
            "title": display_title,
            "url": url,
            "createdAt": datetime.now().isoformat()
        })
        save_webshare_index(index_data)
        
        # Git push
        print(f"📤 Pushing webshare: {filename}.html")
        git_success, git_message = git_push(f"Add webshare: {display_title}")
        
        return jsonify({
            "success": True,
            "filename": f"{filename}.html",
            "title": display_title,
            "url": url,
            "gitPushed": git_success,
            "message": f"Page created! {git_message}"
        })
        
    except Exception as e:
        print(f"❌ Webshare error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/webshare/history', methods=['GET'])
def get_webshare_history():
    """Get webshare history."""
    try:
        index_data = load_webshare_index()
        return jsonify({
            "success": True,
            "pages": index_data.get("pages", [])
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 VAAX Admin Server Started")
    print("=" * 60)
    print("Server running at: http://localhost:5555")
    print("Endpoints:")
    print("  - POST /trigger-send  : Send pending notifications")
    print("  - POST /webshare      : Create webshare page")
    print("  - GET  /webshare/history : Get webshare history")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5555, debug=False)

