import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from scripts.analyze_youtube import process_youtube_url
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# Enable CORS for the frontend hosted on GitHub Pages or locally
CORS(app)

API_KEY = os.getenv("OPENAI_API_KEY")

@app.route('/api/analyze-youtube', methods=['POST'])
def analyze_youtube():
    if not API_KEY:
        return jsonify({"success": False, "message": "OPENAI_API_KEY environment variable is missing in the server environment."}), 500

    data = request.json
    url = data.get("url")
    
    if not url:
        return jsonify({"success": False, "message": "YouTube URL is required."}), 400
        
    print(f"[*] Received request to analyze YouTube URL: {url}")
    result = process_youtube_url(url, API_KEY)
    
    return jsonify(result)

if __name__ == '__main__':
    print("🚀 YouTube Analyzer Server running on http://localhost:5556")
    try:
        app.run(port=5556, debug=True)
    except Exception as e:
        print(f"Error starting server: {e}")
