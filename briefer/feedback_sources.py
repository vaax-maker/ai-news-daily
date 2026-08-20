#!/usr/bin/env python3
"""사용자 피드백 소스 fetcher — Reddit · Hacker News · 긱뉴스.

각 fetcher는 정규화 아이템 리스트를 반환한다:
  {"source": "<표시명>", "text": "<제목. 본문 발췌>", "url": "<링크>", "score": <int>}
네트워크/파싱 실패는 조용히 빈 리스트(해당 소스 스킵). stdlib(urllib)만 사용.
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import quote

# Reddit는 봇 UA에 403 → 브라우저 UA + .rss(Atom) 경로만 허용. HN/긱뉴스도 무해.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_HTMLTAG = re.compile(r"<[^>]+>")
_ATOM = "{http://www.w3.org/2005/Atom}"
_REDDIT_NOISE = re.compile(r"submitted by\s+/u/\S+|to\s+r/\S+|\[link\]|\[comments\]", re.I)


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_json(url: str, timeout: int = 15) -> dict:
    return json.loads(_get(url, timeout).decode("utf-8", "replace"))


def _clean(s: str, n: int = 600) -> str:
    s = _HTMLTAG.sub(" ", s or "")
    s = re.sub(r"&#\d+;|&[a-z]+;", " ", s)
    s = _REDDIT_NOISE.sub(" ", s)
    s = re.sub(r"/u/\S+|/r/\w+", " ", s)          # 개인식별(유저명) 제거
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def _atom_entries(raw: bytes) -> list[dict]:
    """Atom 피드 → [{title, text, url}]. Reddit·긱뉴스 공용."""
    root = ET.fromstring(raw)
    out = []
    for e in root.iter(f"{_ATOM}entry"):
        title = (e.findtext(f"{_ATOM}title") or "").strip()
        body = (e.findtext(f"{_ATOM}content") or e.findtext(f"{_ATOM}summary") or "")
        link = ""
        for ln in e.iter(f"{_ATOM}link"):
            href = ln.get("href")
            if href and (ln.get("rel") in (None, "alternate")):
                link = href
                break
        out.append({"title": title, "text": _clean(f"{title}. {body}"), "url": link})
    return out


# ---- Reddit (public JSON; UA 필수) ----
REDDIT_SUBS = ["ClaudeAI", "ChatGPT", "OpenAI", "LocalLLaMA", "cursor",
               "ChatGPTCoding", "singularity"]


def fetch_reddit(subs: list[str] | None = None, per_sub: int = 10,
                 total_cap: int = 45) -> list[dict]:
    items = []
    subs = subs or REDDIT_SUBS
    for idx, sub in enumerate(subs):
        if idx:
            time.sleep(3)          # Reddit .rss rate-limit(연속 요청 429) 회피
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"      # .json은 403 → Atom .rss
        entries = None
        for attempt in range(2):   # 429면 1회 더(백오프)
            try:
                entries = _atom_entries(_get(url))
                break
            except Exception as e:  # noqa
                if attempt == 0:
                    time.sleep(5)
                    continue
                print(f"[reddit] r/{sub} 스킵: {type(e).__name__}", file=sys.stderr)
        if entries is None:
            continue
        for en in entries[:per_sub]:
            if len(en["text"]) < 12:
                continue
            items.append({"source": f"Reddit r/{sub}", "text": en["text"],
                          "url": en["url"], "score": 0})
    print(f"[reddit] {len(items)}건", file=sys.stderr)
    return items[:total_cap]


# ---- Hacker News (Algolia API) ----
HN_KEYWORDS = ["ChatGPT", "Claude", "Gemini", "Cursor", "LLM agent", "Copilot"]


def fetch_hn(keywords: list[str] | None = None, since_h: int = 48,
             per_kw: int = 12, total_cap: int = 40) -> list[dict]:
    cutoff = int(time.time()) - since_h * 3600
    seen, items = set(), []
    for kw in (keywords or HN_KEYWORDS):
        url = (f"https://hn.algolia.com/api/v1/search?query={quote(kw)}"
               f"&tags=story&numericFilters=created_at_i>{cutoff}&hitsPerPage={per_kw}")
        try:
            data = _get_json(url)
        except Exception as e:  # noqa
            print(f"[hn] '{kw}' 스킵: {type(e).__name__}", file=sys.stderr)
            continue
        for h in data.get("hits", []):
            oid = h.get("objectID")
            if oid in seen:
                continue
            seen.add(oid)
            title = h.get("title") or h.get("story_title") or ""
            text = _clean(f"{title}. {h.get('story_text') or h.get('comment_text') or ''}")
            if len(text) < 12:
                continue
            items.append({"source": "Hacker News", "text": text,
                          "url": f"https://news.ycombinator.com/item?id={oid}",
                          "score": int(h.get("points") or 0),
                          "comments": int(h.get("num_comments") or 0)})
    items.sort(key=lambda x: x["score"], reverse=True)
    print(f"[hn] {len(items)}건", file=sys.stderr)
    return items[:total_cap]


# ---- 긱뉴스 (RSS) — AI 관련만 ----
GEEKNEWS_RSS = "https://news.hada.io/rss/news"
_AI_KW = re.compile(r"(AI|인공지능|GPT|LLM|Claude|Gemini|OpenAI|Anthropic|에이전트|"
                    r"모델|머신러닝|딥러닝|생성형|챗봇|코파일럿|Copilot|Cursor|프롬프트)", re.I)


def fetch_geeknews(limit: int = 25, total_cap: int = 20) -> list[dict]:
    try:
        entries = _atom_entries(_get(GEEKNEWS_RSS))       # 긱뉴스도 Atom(<entry>)
    except Exception as e:  # noqa
        print(f"[geeknews] 스킵: {type(e).__name__}", file=sys.stderr)
        return []
    items = []
    for en in entries:
        if not _AI_KW.search(en["text"]):
            continue
        items.append({"source": "긱뉴스", "text": en["text"], "url": en["url"], "score": 0})
        if len(items) >= limit:
            break
    print(f"[geeknews] {len(items)}건", file=sys.stderr)
    return items[:total_cap]


def fetch_all() -> dict[str, list[dict]]:
    """소스별 아이템. 실패 소스는 빈 리스트."""
    return {"reddit": fetch_reddit(), "hn": fetch_hn(), "geeknews": fetch_geeknews()}


if __name__ == "__main__":
    for name, items in fetch_all().items():
        print(f"\n=== {name}: {len(items)} ===")
        for x in items[:3]:
            print(f"  [{x['source']}|{x['score']}] {x['text'][:90]}")
