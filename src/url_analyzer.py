"""
URL Analyzer — FastAPI 독립 서버

실행 방법:
    pip install -r requirements-extra.txt
    uvicorn src.url_analyzer:app --reload --port 8000

엔드포인트:
    POST /analyze  {"url": "https://..."}  → ParsedContent JSON
    GET  /bento?url=https://...            → Bento Grid HTML

메인 파이프라인(main.py)과 독립 실행됨. requirements-extra.txt 의존.
"""
from __future__ import annotations

from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.parser.base import BaseParser, ParsedContent
from src.parser.youtube import YouTubeParser
from src.parser.article import ArticleParser

app = FastAPI()


class AnalyzeRequest(BaseModel):
    url: str


class ParserRegistry:
    def __init__(self):
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)

    def get_parser(self, url: str) -> BaseParser:
        for parser in self._parsers:
            if parser.can_parse(url):
                return parser
        raise ValueError(f"No parser available for: {url}")


_registry = ParserRegistry()
_registry.register(YouTubeParser())
_registry.register(ArticleParser())  # fallback: can_parse() always True


def analyze_url(url: str) -> dict:
    """URL을 분석하여 ParsedContent를 dict로 반환."""
    parser = _registry.get_parser(url)
    result: ParsedContent = parser.parse_with_fallback(url)
    return {
        "url": url,
        "title": result.title,
        "content": result.content,
        "source": result.source,
        "date": result.date,
        "keywords": result.keywords,
        "related_links": result.related_links,
    }


def render_bento_html(items: List[dict]) -> str:
    html = [
        "<html><head><style>"
        " .card{border:1px solid #ddd;padding:10px;margin:6px;flex:1;}"
        " .grid{display:flex;flex-wrap:wrap;}"
        "</style></head><body>"
    ]
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


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        result = analyze_url(req.url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bento")
async def bento(url: str):
    data = analyze_url(url)
    items = [{"title": data.get("title"), "content": data.get("content"), "source": data.get("source")}]
    return render_bento_html(items)
