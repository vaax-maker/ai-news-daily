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

# Configure Flask to serve static files from 'docs' folder
app = Flask(__name__, static_folder='docs', static_url_path='')
CORS(app)  # Enable CORS for admin panel access

@app.route('/')
@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    """Serve the admin.html page directly."""
    return app.send_static_file('admin.html')


class TitleExtractor(HTMLParser):
    """Extract title from HTML content."""
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_h1 = False
        self.title = ""
        self.h1 = ""
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "h1":
            self.in_h1 = True
    
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
        elif tag.lower() == "h1":
            self.in_h1 = False
    
    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1 and not self.h1:  # Only capture first h1
            self.h1 += data


def extract_title(html_content):
    """Extract title from HTML. Prefer h1 over title tag for actual content title."""
    parser = TitleExtractor()
    try:
        parser.feed(html_content)
        # Prefer h1 (actual content title) over title tag (document title)
        h1_title = parser.h1.strip()
        if h1_title:
            return h1_title
        title = parser.title.strip()
        return title if title else None
    except:
        return None


import secrets
import string

def generate_short_id(length=8):
    """Generate a random short ID."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_unique_filename():
    """Generate a unique short filename."""
    while True:
        filename = generate_short_id()
        if not os.path.exists(os.path.join(WEBSHARE_DIR, f"{filename}.html")):
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
        
        # 3. Pull any remote changes (rebase) with Stash protection
        # If there are uncommitted changes (though we just committed usually), stash them
        subprocess.run(["git", "stash"], cwd=PROJECT_ROOT, check=False, capture_output=True)
        
        try:
            subprocess.run(["git", "pull", "--rebase"], cwd=PROJECT_ROOT, check=True, 
                          capture_output=True, timeout=60)
        finally:
            # Always try to pop stash if we stashed something
            subprocess.run(["git", "stash", "pop"], cwd=PROJECT_ROOT, check=False, capture_output=True)
        
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
        
        # Generate unique filename (Random Short ID)
        filename = get_unique_filename()
        
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
        
        # Post to Blogger (if configured)
        blogger_url = None
        blogger_error = None
        try:
            from src.utils.blogger_client import post_to_blogger, is_blogger_configured
            if is_blogger_configured():
                print(f"📝 Posting to Blogger: {display_title}")
                result = post_to_blogger(display_title, html_content)
                blogger_url = result.get('url')
                print(f"✅ Blogger post created: {blogger_url}")
        except Exception as e:
            blogger_error = str(e)
            print(f"⚠️ Blogger posting failed: {e}")
        
        # Git push
        print(f"📤 Pushing webshare: {filename}.html")
        git_success, git_message = git_push(f"Add webshare: {display_title}")
        
        return jsonify({
            "success": True,
            "filename": f"{filename}.html",
            "title": display_title,
            "url": url,
            "bloggerUrl": blogger_url,
            "bloggerError": blogger_error,
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


@app.route('/blogger', methods=['POST'])
def post_to_blogger_endpoint():
    """Post content to Blogger only (for serverless webshare)."""
    try:
        data = request.get_json()
        title = data.get('title', 'Untitled')
        html_content = data.get('html', '').strip()
        
        if not html_content:
            return jsonify({"success": False, "message": "HTML content is required"}), 400
        
        from src.utils.blogger_client import post_to_blogger, is_blogger_configured
        
        if not is_blogger_configured():
            return jsonify({"success": False, "message": "Blogger not configured"}), 400
        
        print(f"📝 Posting to Blogger: {title}")
        result = post_to_blogger(title, html_content)
        print(f"✅ Blogger post created: {result.get('url')}")
        
        return jsonify({
            "success": True,
            "bloggerUrl": result.get('url'),
            "message": "Posted to Blogger successfully!"
        })
        
    except Exception as e:
        print(f"❌ Blogger error: {e}")
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

