from __future__ import annotations

import re
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI()


class AnalyzeRequest(BaseModel):
    url: str


def is_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube.com|youtu.be)", url, re.IGNORECASE))


def extract_video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?]|$)", url)
    if m:
        return m.group(1)
    return None


def fetch_youtube_transcript(video_id: str) -> List[str]:
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)  # type: ignore[attr-defined]
        lines = [entry["text"] for entry in transcript_list]
        return lines
    except Exception:
        return []


def fetch_article(url: str) -> dict:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = " ".join([t.get_text(strip=True) for t in soup.find_all(['title', 'h1'])]) or url
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    content = "\n".join(paragraphs[:20]) if paragraphs else resp.text
    return {"title": title, "content": content, "source": url}


def render_bento_html(items: List[dict]) -> str:
    html = ["<html><head><style> .card{border:1px solid #ddd;padding:10px;margin:6px;flex:1;} .grid{display:flex;flex-wrap:wrap;} </style></head><body>"]
    html.append('<div class="grid">')
    for it in items:
        t = it.get("title", "")
        c = it.get("content", "")
        s = it.get("source", "URL")
        html.append("<div class=\"card\">")
        html.append(f"<h3>{t}</h3>")
        html.append(f"<p>{c}</p>")
        html.append(f"<small>Source: {s}</small>")
        html.append("</div>")
    html.append("</div>")
    html.append("</body></html>")
    return "".join(html)


def analyze_url(url: str) -> dict:
    data = {"url": url, "title": None, "content": None, "transcript": None, "source": url}
    if is_youtube_url(url):
        vid = extract_video_id(url)
        data["title"] = "YouTube Video"
        transcript = fetch_youtube_transcript(vid) if vid else []
        data["transcript"] = transcript
        if transcript:
            data["content"] = "\n".join(transcript)
        else:
            data["content"] = "Transcript unavailable"
        return data
    article = fetch_article(url)
    data["title"] = article.get("title")
    data["content"] = article.get("content")
    return data


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    url = req.url
    try:
        result = analyze_url(url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bento")
async def bento(url: str):
    data = analyze_url(url)
    items = [{"title": data.get("title"), "content": data.get("content"), "source": data.get("source")}]
    html = render_bento_html(items)
    return html
