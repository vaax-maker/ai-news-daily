import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys

# Initialize Firebase
cred_path = "/Users/fovea/Documents/vsc-codex/VAAXfinal/vaax-board-firebase-adminsdk-fbsvc-67b91f8d90.json"
if not os.path.exists(cred_path):
    print(f"Error: Firebase credential not found at {cred_path}")
    sys.exit(1)

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Find the document
filename_part = "2026-01-04_230435.html"
print(f"Searching for article with archivePath containing {filename_part}...")

# Note: searching by substring in Firestore is hard.
# We'll search by dateStr if possible or list all success items (likely few).
# Or just list all manual_articles.

docs = db.collection('manual_articles').get()
found = False
for doc in docs:
    data = doc.to_dict()
    path = data.get('archivePath', '')
    if filename_part in path:
        print(f"Found document: {doc.id}")
        doc.reference.update({
            'status': 'pending',
            'summary': '', # Clear summary to force regeneration
            'image': ''    # Clear image to force regeneration
        })
        print("Status reset to 'pending'. cleared summary/image.")
        found = True
        break

if not found:
    print("Document not found.")
