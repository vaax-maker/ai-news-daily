import re
import requests
from bs4 import BeautifulSoup
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from src.parser.base import BaseParser, ParsedContent

class YouTubeParser(BaseParser):
    def can_parse(self, url: str) -> bool:
        return 'youtube.com' in url or 'youtu.be' in url
    
    def parse(self, url: str) -> ParsedContent:
        video_id = self._extract_video_id(url)
        transcript = self._get_transcript(video_id)
        metadata = self._get_metadata(url)
        
        return ParsedContent(
            title=metadata.get('title', 'YouTube Video'),
            source='YouTube',
            date=metadata.get('date'),
            content=transcript,
            keywords=self._extract_keywords(metadata.get('title', '')),
            related_links=[]
        )
    
    def _extract_video_id(self, url: str) -> str:
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError("Invalid YouTube URL")
    
    def _get_transcript(self, video_id: str) -> str:
        try:
            transcript_api = YouTubeTranscriptApi
            transcript = getattr(transcript_api, 'get_transcript')(video_id, languages=['ko', 'en'])
            return ' '.join([t['text'] for t in transcript])
        except Exception:
            return ""
    
    def _get_metadata(self, url: str) -> dict:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers)
        soup = BeautifulSoup(resp.text, 'html.parser')
        title_tag = soup.find('meta', property='og:title')
        if title_tag and title_tag.get('content'):
            title = str(title_tag.get('content')).strip()
        else:
            t = soup.find('title')
            title = t.get_text().strip() if t else 'Untitled'
        return {'title': title, 'date': None}
    
    def _extract_keywords(self, title: str) -> List[str]:
        return []
