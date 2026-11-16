"""Fetch and extract readable article text from public news pages."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser

from aidaily.integrations.http import request_bytes


_TARGET_MARKERS = {
    "article", "article-body", "article_body", "articlebody", "article-content",
    "article_content", "newsct_article", "dic_area", "news-article-body",
}
_BLOCK_TAGS = {"p", "div", "section", "li", "br", "h2", "h3", "blockquote"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
              "param", "source", "track", "wbr"}


def _clean(value: str) -> str:
    value = html.unescape(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _json_article_body(value):
    if isinstance(value, dict):
        body = value.get("articleBody")
        if isinstance(body, str) and _clean(body):
            return _clean(body)
        for child in value.values():
            found = _json_article_body(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _json_article_body(child)
            if found:
                return found
    return ""


class _ArticleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture_depth = 0
        self.parts = []
        self.article_depth = 0
        self.article_parts = []
        self.script_json = False
        self.script_parts = []
        self.json_bodies = []

    @staticmethod
    def _is_target(attrs):
        values = " ".join(str(value or "").casefold() for _, value in attrs)
        tokens = set(re.split(r"[^a-z0-9_-]+", values))
        return bool(tokens & _TARGET_MARKERS)

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        attr_map = {str(key).casefold(): str(value or "") for key, value in attrs}
        if tag == "script" and "ld+json" in attr_map.get("type", "").casefold():
            self.script_json = True
            self.script_parts = []
        if self.capture_depth and tag not in _VOID_TAGS:
            self.capture_depth += 1
        elif self._is_target(attrs):
            self.capture_depth = 1
        if self.article_depth and tag not in _VOID_TAGS:
            self.article_depth += 1
        elif tag == "article":
            self.article_depth = 1
        if tag in _BLOCK_TAGS:
            if self.capture_depth:
                self.parts.append(" ")
            if self.article_depth:
                self.article_parts.append(" ")

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if self.script_json and tag == "script":
            try:
                body = _json_article_body(json.loads("".join(self.script_parts)))
                if body:
                    self.json_bodies.append(body)
            except (TypeError, ValueError):
                pass
            self.script_json = False
            self.script_parts = []
        if self.capture_depth:
            self.capture_depth -= 1
        if self.article_depth:
            self.article_depth -= 1

    def handle_data(self, data):
        if self.script_json:
            self.script_parts.append(data)
        if self.capture_depth:
            self.parts.append(data)
        if self.article_depth:
            self.article_parts.append(data)


def extract_article_text(document: str, max_chars: int = 12000) -> str:
    """Extract the best article body candidate from HTML without extra dependencies."""
    parser = _ArticleHTMLParser()
    parser.feed(document or "")
    # Prefer explicit articleBody JSON-LD, then known news-body containers, and only
    # then a generic <article>. Choosing the longest candidate can accidentally pick
    # navigation/comments surrounding a short article.
    groups = [parser.json_bodies, [_clean("".join(parser.parts))],
              [_clean("".join(parser.article_parts))]]
    for candidates in groups:
        substantial = [candidate for candidate in candidates if len(candidate) >= 160]
        if substantial:
            return max(substantial, key=len)[:max_chars].strip()
    return ""


def fetch_article_text(url: str, timeout: int = 20, max_chars: int = 12000) -> str:
    """Download one public article and return its readable body text."""
    if not str(url or "").startswith(("http://", "https://")):
        return ""
    raw, headers = request_bytes(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        },
        timeout=timeout,
    )
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        document = raw.decode(encoding, "replace")
    except LookupError:
        document = raw.decode("utf-8", "replace")
    return extract_article_text(document, max_chars=max_chars)
