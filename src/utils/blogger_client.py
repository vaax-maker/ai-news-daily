#!/usr/bin/env python3
"""
Blogger API client for posting HTML content.
Uses OAuth 2.0 for authentication.
"""
import os
import pickle
from pathlib import Path

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes required for Blogger API
SCOPES = ['https://www.googleapis.com/auth/blogger']

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / 'blogger_credentials.json'
TOKEN_FILE = PROJECT_ROOT / 'blogger_token.pickle'


def get_blogger_service():
    """
    Get authenticated Blogger API service.
    First run will open browser for OAuth authentication.
    """
    creds = None
    
    # Load saved token if exists
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {CREDENTIALS_FILE}\n"
                    "Please download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save token for future use
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('blogger', 'v3', credentials=creds)


def get_blog_id(service=None):
    """
    Get the first blog ID for the authenticated user.
    """
    if service is None:
        service = get_blogger_service()
    
    blogs = service.blogs().listByUser(userId='self').execute()
    
    if not blogs.get('items'):
        raise ValueError("No blogs found for this user. Please create a blog first.")
    
    return blogs['items'][0]['id']


def post_to_blogger(title: str, html_content: str, blog_id: str = None) -> dict:
    """
    Post HTML content to Blogger.
    
    Args:
        title: Post title
        html_content: HTML content of the post
        blog_id: Optional blog ID (auto-detected if not provided)
    
    Returns:
        dict with 'id', 'url', 'title' of created post
    """
    service = get_blogger_service()
    
    if blog_id is None:
        blog_id = get_blog_id(service)
    
    body = {
        'kind': 'blogger#post',
        'title': title,
        'content': html_content
    }
    
    post = service.posts().insert(blogId=blog_id, body=body).execute()
    
    return {
        'id': post['id'],
        'url': post['url'],
        'title': post['title']
    }


def is_blogger_configured() -> bool:
    """Check if Blogger is properly configured."""
    return CREDENTIALS_FILE.exists()


if __name__ == '__main__':
    # Test authentication
    print("Testing Blogger API authentication...")
    try:
        service = get_blogger_service()
        blog_id = get_blog_id(service)
        print(f"✅ Successfully authenticated!")
        print(f"📝 Blog ID: {blog_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
