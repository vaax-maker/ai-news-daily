#!/usr/bin/env python3
"""
Simple Flask server to trigger immediate message sending from admin panel.
Run this server locally: python3 admin_server.py
"""
from flask import Flask, jsonify
from flask_cors import CORS
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set the service account path
os.environ["FIREBASE_SERVICE_ACCOUNT"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json"
)

app = Flask(__name__)
CORS(app)  # Enable CORS for admin panel access

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

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 VAAX Admin Server Started")
    print("=" * 60)
    print("Server running at: http://localhost:5555")
    print("Admin panel can now use 'Send Now' button!")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5555, debug=False)
