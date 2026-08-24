#!/usr/bin/env python3
"""추가 AI뉴스 소스 fetcher — 주말 커버리지 + 평일 보강 (ISOLATED, 라이브 미배선).

기존 파이프라인은 aiofmodu.com(Firestore) 한 곳에서만 하루 5건을 뽑는다
(briefer/source.py). 이 모듈은 4개 외부 소스를 추가로 긁어 **동일한 스토리 스키마**
`{n, emoji, headline, body, takeaway, url}` 로 정규화한다(모두 한국어).

소스(2026-08-24 실측):
  1. MIT Technology Review (AI 섹션)  — RSS ✅  https://www.technologyreview.com/topic/artificial-intelligence/feed/  (영어→번역)
  2. CB Insights (research)           — RSS ✅  https://www.cbinsights.com/research/feed/                              (영어→번역)
  3. aibase.com                       — RSS ❌ (Next.js SPA, /rss·/feed 전부 404) → /news 리스팅 HTML 스크레이핑  (영어→번역)
  4. AI타임스 (aitimes.com)           — RSS ✅  https://www.aitimes.com/rss/allArticle.xml                           (한국어)

설계 원칙(feedback_sources.py 패턴 재사용):
  - 브라우저 User-Agent, RSS/Atom 파싱, 타임아웃.
  - **소스별 try/except**: 한 피드가 죽어도 나머지는 계속 (fetch_extra는 절대 예외 전파 안 함).
  - **날조 금지**: 실제 피드/페이지 내용만. 원문 URL 보존.
  - 영어 소스는 briefer/llm.py(OpenRouter)로 한국어 번역+요약. 키 없으면 해당 소스 to_stories 스킵(가짜 생성 안 함).

두 진입점:
  - fetch_extra(since_days=3, limit_per_source=5) -> list[raw article]
        raw = {"source","title","url","body","published"(datetime|None),"lang"}
  - to_stories(raw_articles) -> list[{n,emoji,headline,body,takeaway,url}]  (한국어)
"""
from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import urllib.request

try:
    from briefer import llm  # OpenRouter 공통 클라이언트
except Exception:  # 단독 실행(python3 briefer/extra_sources.py) 폴백
    import importlib
    llm = importlib.import_module("llm") if __name__ == "__main__" else None

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_HTMLTAG = re.compile(r"<[^>]+>")

# 요약/번역 모델 사슬 — 확정(2026-08-24). llm.complete_json 의 models= 로 전달.
#   1순위 openai/gpt-5.6-terra → 폴백 google/gemini-3.1-flash-lite → deepseek/deepseek-v4-flash.
# 환경변수 EXTRA_NEWS_MODEL(쉼표구분)로 통째 오버라이드 가능. Hermes 미사용(OpenRouter HTTP 직결).
MODELS = [m.strip() for m in os.environ.get(
    "EXTRA_NEWS_MODEL",
    "openai/gpt-5.6-terra,google/gemini-3.1-flash-lite,deepseek/deepseek-v4-flash"
).split(",") if m.strip()]

# 실측 확정 피드 URL
FEEDS = {
    "MIT Tech Review": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
    "CB Insights":     "https://www.cbinsights.com/research/feed/",
    "AI타임스":         "https://www.aitimes.com/rss/allArticle.xml",
    # aibase는 RSS 없음 → 리스팅 HTML 스크레이핑
    "aibase":          "https://www.aibase.com/news",
}

# 소스별 발행 빈도 편차가 큼 → 최신성 창을 소스별로 완화.
# MIT AI섹션은 주간 단위(느림)라 since_days=3이면 매일 0건이 됨(실측). 배수로 넓힌다.
_RECENCY_MULT = {
    "MIT Tech Review": 3,   # 저빈도(주간) → 3배 창
    "CB Insights":     2,   # 리서치, 중빈도
    "aibase":          1,   # 고빈도(리스팅 최신순)
    "AI타임스":         1,   # 고빈도(하루 수십건)
}

# 소스별 발행 상한 — 확정(2026-08-24): 각 2건 → 추가 8 + aiofmodu 5 = 하루 총 13건 목표.
# CB는 인터뷰 가치를 살려 유지하되 3→2로 트림. 환경변수로 오버라이드:
#   EXTRA_NEWS_LIMITS="MIT Tech Review:2,CB Insights:2,aibase:2,AI타임스:2"
_DEFAULT_LIMITS = {
    "MIT Tech Review": 2, "CB Insights": 2, "aibase": 2, "AI타임스": 2,
}


def _parse_limits(env_val: str | None) -> dict:
    limits = dict(_DEFAULT_LIMITS)
    for pair in (env_val or "").split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        name, _, num = pair.rpartition(":")
        name = name.strip()
        if name in limits and num.strip().isdigit():
            limits[name] = int(num.strip())
    return limits


LIMITS = _parse_limits(os.environ.get("EXTRA_NEWS_LIMITS"))

# --- 관련성 필터 (사용자 결정 2026-08-24) ---
# 소스별로 다르게 적용:
#   · CB Insights : AI 관련이면 통과 (CEO/임원 인터뷰·산업계 반응·전략 방향 = 원하는 콘텐츠라 유지).
#   · MIT/aibase/AI타임스 : "기술중심"으로 좁힘 (연구·모델·기술 발전 선호, 순수 비즈/오피니언 강등).
#     — 단, 과잉 드롭 방지: 기술신호가 있으면 통과, 기술신호가 없고 '비즈/오피니언 신호'만 있으면 스킵.

# (1) 기본 AI 관련성 — CB의 게이트 + 다른 소스의 1차 게이트.
_AI_KW = re.compile(
    r"\b(AI|A\.I\.|artificial intelligence|machine learning|deep learning|"
    r"LLM|GPT|ChatGPT|Claude|Gemini|Llama|OpenAI|Anthropic|DeepSeek|Mistral|"
    r"neural|generative|agent|copilot|inference|transformer|diffusion|chatbot|"
    r"NVIDIA|GPU|foundation model|multimodal|robot|autonomous)\b"
    r"|인공지능|생성형|머신러닝|딥러닝|모델|챗봇|에이전트|반도체|엔비디아|"
    r"오픈AI|앤스로픽|딥시크|자율|로봇|추론|프롬프트|초거대|파운데이션",
    re.I,
)

# (2) 기술중심 신호 — 있으면 MIT/aibase/aitimes 통과(선호).
_TECH_KW = re.compile(
    r"\b(model|models|research|benchmark|open[- ]?source|weights|parameters?|"
    r"training|fine[- ]?tun\w*|inference|architecture|multimodal|reasoning|"
    r"agent\w*|transformer|diffusion|LLM|GPU|chip|semiconductor|dataset|"
    r"algorithm|API|SDK|release[ds]?|launch\w*|update[ds]?|capabilit\w*|"
    r"context window|token\w*|embedding|RAG|quantiz\w*|distill\w*)\b"
    r"|모델|연구|논문|벤치마크|오픈소스|가중치|파라미터|학습|훈련|파인튜닝|"
    r"추론|아키텍처|멀티모달|에이전트|트랜스포머|반도체|칩|데이터셋|알고리즘|"
    r"출시|공개|업데이트|성능|컨텍스트|토큰|임베딩|양자화|경량화|기술",
    re.I,
)

# (2b) '강한 AI 신호' — 맨 'AI' 부분일치가 아니라 실질 AI 주제어.
#   tech-focus 소스에서 기술신호가 없을 때, 이게 있어야만 기본통과(캡션 'AI' 오탐 차단).
_STRONG_AI_KW = re.compile(
    r"\b(artificial intelligence|machine learning|deep learning|LLM|GPT|ChatGPT|"
    r"Claude|Gemini|Llama|OpenAI|Anthropic|DeepSeek|Mistral|generative|neural|"
    r"chatbot|copilot|multimodal|foundation model)\b"
    r"|인공지능|생성형|머신러닝|딥러닝|챗봇|초거대|오픈AI|앤스로픽|딥시크|"
    r"생성\s*AI|AI\s*모델|AI\s*에이전트|AI\s*반도체|AI\s*칩",
    re.I,
)

# (3) 비즈/오피니언 신호 — 기술신호가 전혀 없을 때 이것만 있으면 MIT/aibase/aitimes에서 강등(스킵).
_BIZ_OPINION_KW = re.compile(
    r"\b(funding|raises?|raised|valuation|IPO|acquisition|merger|stock|shares|"
    r"revenue|earnings|opinion|editorial|op[- ]?ed|column|interview|hiring|"
    r"layoff\w*|lawsuit|regulation|policy|partnership|investment|投資)\b"
    r"|투자|유치|밸류에이션|상장|인수|합병|주가|매출|실적|칼럼|사설|오피니언|"
    r"인터뷰|채용|해고|소송|규제|정책|제휴|투자유치",
    re.I,
)


def _passes_source_filter(name: str, blob: str) -> bool:
    """소스별 관련성 게이트. blob = 제목+카테고리+본문."""
    ai = bool(_AI_KW.search(blob))
    tech = bool(_TECH_KW.search(blob))
    if name == "CB Insights":
        return ai  # AI 관련이면 인터뷰·전략·산업반응 전부 유지(기술 여부 무관)
    # MIT / aibase / AI타임스 → 기술중심으로 좁힘(라이트 휴리스틱).
    # 관련성은 'AI 신호 OR 기술 신호'로 인정(기술 콘텐츠 자체가 원하는 대상).
    if not (ai or tech):
        return False
    if tech:
        return True  # 기술신호 있으면 통과(선호)
    if _BIZ_OPINION_KW.search(blob):
        return False  # 기술신호 없고 비즈/오피니언 신호만 → 강등
    # 기술·비즈 신호 모두 없음: 맨 'AI' 부분일치(예: 썸네일 캡션)만으로는 통과 불가.
    # 실질 AI 주제어(강한 신호)가 있을 때만 통과 → 비AI 지역/사회 기사 오탐 차단.
    return bool(_STRONG_AI_KW.search(blob))


# AI타임스 썸네일 캡션 아티팩트 — 본문 앞에 'AI 생성 영상'/'AI 생성 이미지'가 붙어
# 관련성 필터에 가짜 'AI' 신호를 만든다(실측). 필터·요약 전에 제거.
_AITIMES_CAPTION = re.compile(r"^\s*AI\s*생성\s*(영상|이미지|사진|그림)\s*", re.I)


def _clean(s: str, n: int = 1200) -> str:
    s = unescape(s or "")
    s = _HTMLTAG.sub(" ", s)
    s = re.sub(r"&#\d+;|&[a-z]+;", " ", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _AITIMES_CAPTION.sub("", s)  # 썸네일 캡션 제거
    return s[:n]


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "*/*",
                      "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ----------------------------------------------------------------------------
# 날짜 파싱 (RFC822 pubDate, aitimes 'YYYY-MM-DD HH:MM:SS', ISO)
# ----------------------------------------------------------------------------
def _parse_date(raw: str | None):
    if not raw:
        return None
    raw = raw.strip()
    try:  # RFC822 (MIT/CB): 'Thu, 20 Aug 2026 15:42:39 +0000'
        dt = parsedate_to_datetime(raw)
        if dt:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 6], fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _is_recent(dt, since_days: int) -> bool:
    if dt is None:
        return True  # 날짜 미상(aibase 리스팅 등) → 최신순 상단이라 통과
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    return dt >= cutoff


# ----------------------------------------------------------------------------
# 헤드라인 정규화 — dedup 3계층 공통(소문자·기호/공백 제거·앞 24자)
# ----------------------------------------------------------------------------
def _norm_headline(h: str) -> str:
    return re.sub(r"[\s\W_]+", "", (h or "").lower())[:24]


# ----------------------------------------------------------------------------
# 교차일 영속 seen-store (dedup layer c)
#   포맷: {"entries": [{"url","headline_norm","date"(YYYY-MM-DD)}...]}
#   기본 경로 data/extra_seen.json — DRY-RUN 시 EXTRA_SEEN_STORE 로 TEMP 경로 지정.
# ----------------------------------------------------------------------------
import json  # noqa: E402  (파일 상단 import군과 분리해 이 블록의 의존 명시)

_DEFAULT_SEEN_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "extra_seen.json")
_SEEN_MAX_AGE_DAYS = 30


def seen_store_path() -> str:
    """seen-store 경로. 환경변수 EXTRA_SEEN_STORE 가 있으면 그걸 사용(DRY-RUN용 TEMP)."""
    return os.environ.get("EXTRA_SEEN_STORE", "").strip() or _DEFAULT_SEEN_PATH


def load_seen(path: str | None = None) -> dict:
    """seen-store 로드 + 30일 초과 프루닝. 파일 없으면 빈 store."""
    path = path or seen_store_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"urls": set(), "heads": set(), "entries": []}
    entries = data.get("entries", []) if isinstance(data, dict) else []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_SEEN_MAX_AGE_DAYS)).date().isoformat()
    kept = [e for e in entries if (e.get("date") or "9999") >= cutoff]
    urls = {e["url"] for e in kept if e.get("url")}
    heads = {e["headline_norm"] for e in kept if e.get("headline_norm")}
    return {"urls": urls, "heads": heads, "entries": kept}


def is_seen(store: dict, url: str, headline: str) -> bool:
    """교차일 중복 판정: url 완전일치 OR 정규화 헤드라인 일치(교차언어는 url로 최소보장)."""
    if url and url in store["urls"]:
        return True
    hn = _norm_headline(headline)
    return bool(hn) and hn in store["heads"]


def record_seen(store: dict, url: str, headline: str) -> None:
    """선택된 기사를 store에 추가(메모리). save_seen 으로 영속화."""
    hn = _norm_headline(headline)
    if url:
        store["urls"].add(url)
    if hn:
        store["heads"].add(hn)
    store["entries"].append({"url": url, "headline_norm": hn,
                             "date": datetime.now(timezone.utc).date().isoformat()})


def save_seen(store: dict, path: str | None = None) -> None:
    """store를 디스크에 기록(원자적: tmp→rename). 디렉터리 없으면 생성."""
    path = path or seen_store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"entries": store["entries"]}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------
# RSS(<item>) 파서 — MIT / CB Insights / aitimes 공용
# ----------------------------------------------------------------------------
def _rss_items(raw: bytes) -> list[dict]:
    # 일부 피드는 잘못된 XML 선언/BOM → 관대하게 시도
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    out = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title") or "", 300)
        link = (it.findtext("link") or "").strip()
        # description / content:encoded
        desc = it.findtext("description") or ""
        for child in it:
            if child.tag.endswith("encoded") and (child.text or ""):
                desc = child.text
                break
        cats = " ".join((c.text or "") for c in it.findall("category"))
        pub = (it.findtext("pubDate")
               or it.findtext("{http://purl.org/dc/elements/1.1/}date")
               or "")
        out.append({"title": title, "url": link,
                    "body": _clean(desc, 1200),
                    "category": _clean(cats, 200),
                    "published": _parse_date(pub)})
    return out


def _fetch_rss_source(name: str, url: str, since_days: int, limit: int,
                      seen_pred=None) -> list[dict]:
    try:
        items = _rss_items(_get(url))
    except Exception as e:  # noqa
        print(f"[extra:{name}] FETCH FAIL {type(e).__name__}: {str(e)[:120]}  ({url})",
              file=sys.stderr)
        return []
    lang = "ko" if name == "AI타임스" else "en"
    window = since_days * _RECENCY_MULT.get(name, 1)
    picked, seen, skipped_seen = [], set(), 0
    for it in items:
        blob = f"{it['title']} {it['category']} {it['body']}"
        if not _passes_source_filter(name, blob):
            continue
        if not _is_recent(it["published"], window):
            continue
        key = (it["title"] or it["url"]).lower()
        if not it["title"] or key in seen:
            continue
        # 교차일 seen-store 스킵(limit 채우기 전에 걸러 → 더 깊은 신규 후보로 대체).
        if seen_pred and seen_pred(it["url"], it["title"]):
            skipped_seen += 1
            continue
        seen.add(key)
        picked.append({"source": name, "title": it["title"], "url": it["url"],
                       "body": it["body"], "published": it["published"], "lang": lang})
        if len(picked) >= limit:
            break
    print(f"[extra:{name}] {len(picked)}/{len(items)}건 "
          f"(window={window}d, seen-skip={skipped_seen}, feed={url})", file=sys.stderr)
    return picked


# ----------------------------------------------------------------------------
# aibase.com — RSS 없음 → /news 리스팅 스크레이핑 + 기사 og:description 보강
# ----------------------------------------------------------------------------
class _AibaseListParser(HTMLParser):
    """<a href="/news/ID">…title…</a> 추출. 앵커 텍스트에서 'just now . AIbase' 접두 제거."""

    def __init__(self):
        super().__init__()
        self._href = None
        self._buf = []
        self.items = []  # [(href, text)]

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            h = d.get("href", "")
            if re.fullmatch(r"/news/\d+", h or ""):
                self._href = h
                self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.items.append((self._href, " ".join(self._buf)))
            self._href = None
            self._buf = []


def _aibase_clean_title(text: str) -> str:
    t = _clean(text, 300)
    # 리스팅 앵커 접두: "just now . AIbase", "3 hours ago . AIbase" 등
    t = re.sub(r"^\s*(just now|\d+\s*(minute|hour|day|second)s?\s*ago)\s*\.\s*AIbase\s*",
               "", t, flags=re.I)
    t = re.sub(r"^\s*AIbase\s*", "", t, flags=re.I)
    return t.strip()


def _og_meta(html: str, prop: str) -> str | None:
    for pat in (rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"',
                rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"'):
        m = re.search(pat, html, re.I)
        if m:
            return _clean(unescape(m.group(1)), 1200)
    return None


def _fetch_aibase(url: str, since_days: int, limit: int, seen_pred=None) -> list[dict]:
    try:
        html = _get(url).decode("utf-8", "replace")
    except Exception as e:  # noqa
        print(f"[extra:aibase] LIST FAIL {type(e).__name__}: {str(e)[:120]}  ({url})",
              file=sys.stderr)
        return []
    p = _AibaseListParser()
    try:
        p.feed(html)
    except Exception:
        pass
    picked, seen, skipped_seen = [], set(), 0
    for href, text in p.items:  # 리스팅은 최신순(상단이 최근)
        art_url = "https://www.aibase.com" + href
        if art_url in seen:
            continue
        seen.add(art_url)
        title = _aibase_clean_title(text)
        # 교차일 seen-store: URL로 먼저 스킵(상세 fetch 낭비 방지).
        if seen_pred and seen_pred(art_url, title):
            skipped_seen += 1
            continue
        if not title or not _AI_KW.search(title):
            # 리스팅 제목이 짧거나 필터 미스면 상세에서 og:title 재확인
            title = title or ""
        body = ""
        try:  # 상세 페이지 og:description = 실제 요약 문단
            ah = _get(art_url, timeout=15).decode("utf-8", "replace")
            body = _og_meta(ah, "og:description") or ""
            og_t = _og_meta(ah, "og:title")
            if og_t and (not title or len(title) < 12):
                title = og_t
        except Exception as e:  # noqa
            print(f"[extra:aibase] 상세 스킵 {href}: {type(e).__name__}", file=sys.stderr)
        if not title:
            continue
        # og:title 확정 후 헤드라인 기준 seen-store 재확인(교차언어/제목변화 대비).
        if seen_pred and seen_pred(art_url, title):
            skipped_seen += 1
            continue
        # 결정 게이트: aibase는 기술중심 필터(제목+본문 전체로 판정).
        if not _passes_source_filter("aibase", f"{title} {body}"):
            continue
        picked.append({"source": "aibase", "title": title, "url": art_url,
                       "body": body, "published": None, "lang": "en"})
        if len(picked) >= limit:
            break
    print(f"[extra:aibase] {len(picked)}/{len(p.items)}건 "
          f"(seen-skip={skipped_seen}, scrape={url})", file=sys.stderr)
    return picked


# ----------------------------------------------------------------------------
# 공개 진입점 1: fetch_extra
# ----------------------------------------------------------------------------
def fetch_extra(since_days: int = 3, limit_per_source=None, seen_pred=None) -> list[dict]:
    """4개 소스에서 원시 기사 수집. 소스별 격리(한 곳 실패해도 나머지 진행).

    limit_per_source: None → LIMITS(소스별 기본 2). int → 전 소스 동일값. dict → 소스별 개별값.
    seen_pred(url, headline)->bool: 교차일 seen-store 스킵 콜백(limit 채우기 전에 걸러짐).
    """
    if limit_per_source is None:
        limits = dict(LIMITS)
    elif isinstance(limit_per_source, dict):
        limits = {**LIMITS, **limit_per_source}
    else:  # int → 전 소스 동일
        limits = {k: int(limit_per_source) for k in FEEDS}
    raw: list[dict] = []
    for name in ("MIT Tech Review", "CB Insights", "AI타임스"):
        raw += _fetch_rss_source(name, FEEDS[name], since_days,
                                 limits.get(name, 2), seen_pred=seen_pred)
    raw += _fetch_aibase(FEEDS["aibase"], since_days,
                         limits.get("aibase", 2), seen_pred=seen_pred)
    print(f"[extra] 총 {len(raw)}건 수집 (limits={limits})", file=sys.stderr)
    return raw


# ----------------------------------------------------------------------------
# 공개 진입점 2: to_stories  (한국어 정규화)
# ----------------------------------------------------------------------------
_SYS = (
    "너는 한국어 AI뉴스 편집자다. 주어진 기사(제목+본문 발췌)를 한국어 카드로 요약한다. "
    "규칙: (1) 원문 사실만 — 수치·고유명사·인용을 그대로, 창작·과장·추측 절대 금지. "
    "본문에 없는 정보는 넣지 마라. (2) headline: 한국어 45자 이내, 핵심 한 줄. "
    "(3) body: 2~3문장, 완결된 문장체. (4) takeaway: 1문장, '왜 중요한가(함의)'. "
    "(5) 이모지 금지. 출력은 JSON 객체 하나만(코드펜스·설명 금지): "
    '{"headline":"...","body":"...","takeaway":"..."}'
)


def _summarize_ko(art: dict) -> dict | None:
    """한 기사 → {headline, body, takeaway} 한국어. 실패 시 None(가짜 생성 안 함)."""
    if llm is None or not getattr(llm, "KEY", ""):
        return None
    src_lang = "한국어" if art["lang"] == "ko" else "영어"
    user = (f"[출처: {art['source']} · 원문 {src_lang}]\n"
            f"제목: {art['title']}\n"
            f"본문 발췌: {art['body'] or '(본문 없음 — 제목만으로 요약하되 창작 금지)'}\n\n"
            "위 기사를 한국어 JSON 카드로.")
    try:
        obj = llm.complete_json(_SYS, user, models=MODELS, temperature=0.2,
                                timeout=90, max_tokens=600)
    except Exception as e:  # noqa
        print(f"[extra:to_stories] LLM 실패 '{art['title'][:40]}': "
              f"{type(e).__name__}", file=sys.stderr)
        return None
    if not isinstance(obj, dict):
        return None
    h = _clean(str(obj.get("headline") or ""), 90)
    b = _clean(str(obj.get("body") or ""), 500)
    t = _clean(str(obj.get("takeaway") or ""), 200)
    if not h or not b:
        return None
    return {"headline": h, "body": b, "takeaway": t}


# 소스별 이모지(스토리 스키마 emoji 필드)
_EMOJI = {"MIT Tech Review": "🔬", "CB Insights": "📊", "aibase": "🌐", "AI타임스": "📰"}

# URL 도메인 → 깨끗한 소스 라벨(페이지/스토어 표시용). 소스명이 유실돼도 URL로 복원 가능.
_DOMAIN_LABEL = [
    ("technologyreview.com", "MIT Tech Review"),
    ("cbinsights.com",       "CB Insights"),
    ("aibase.com",           "aibase"),
    ("aitimes.com",          "AI타임스"),
]


def source_label(url: str, fallback: str = "") -> str:
    u = (url or "").lower()
    for dom, label in _DOMAIN_LABEL:
        if dom in u:
            return label
    return fallback


def to_stories(raw_articles: list[dict], start_n: int = 6) -> list[dict]:
    """원시 기사 → 파이프라인 스토리 스키마(한국어) 리스트.

    반환: [{n, emoji, headline, body, takeaway, url}]
      - n: 두 자리 문자열('06','07' ...) — aiofmodu 5건(01~05) 뒤에 이어붙이는 가정.
      - 영어 소스(MIT/CB/aibase)는 OpenRouter로 번역+요약. 키 없으면 스킵(날조 금지).
      - 한국어 소스(AI타임스)도 동일 요약기로 헤드라인·함의 정제.
    """
    stories, n = [], start_n
    for art in raw_articles:
        card = _summarize_ko(art)
        if not card:
            continue  # 요약 실패 = 가짜 대신 드롭
        stories.append({
            "n": f"{n:02d}",
            "emoji": _EMOJI.get(art["source"], "🗞️"),
            "headline": card["headline"],
            "body": card["body"],
            "takeaway": card["takeaway"],
            "url": art["url"],
            # 스토리 스키마 확장: 추가 소스 라벨(aiofmodu 5건에는 이 필드 없음 → 렌더가 있으면만 표기).
            "source": source_label(art["url"], art["source"]),
        })
        n += 1
    print(f"[extra:to_stories] {len(stories)}/{len(raw_articles)}건 한국어화", file=sys.stderr)
    return stories


# ----------------------------------------------------------------------------
# 공개 진입점 3: merge_into  (build.py 배선용 — 2줄 호출로 today 확장)
# ----------------------------------------------------------------------------
# (_norm_headline 은 파일 상단에 정의됨 — dedup 3계층 공통.)


def merge_into(today: dict, since_days: int = 3, limit_per_source=None,
               use_seen_store: bool = True) -> dict:
    """today['stories'](aiofmodu 5건) 뒤에 추가 소스 스토리를 append(제자리 변경 + 반환).

    dedup 3계층(중복제거 필수):
      (a) 당일 4개 소스 상호간 — 같은 기사가 두 피드에서 나오면 1건만.
      (b) aiofmodu 당일 5건 대비 — 이미 다룬 건 반복 안 함.
      (c) 교차일 영속 seen-store — RSS 창에 며칠 머무는 기사도 평생 1회만 방출.
          url OR 정규화 헤드라인 일치로 스킵. 선택분은 store에 기록+저장(30일 프루닝).
          경로: EXTRA_SEEN_STORE(TEMP) > data/extra_seen.json. use_seen_store=False면 비활성.

    - n은 기존 스토리 수 다음부터 이어붙임(06,07,...).
    - 추가 소스가 0건이면 today는 그대로(부작용 없음) → 라이브 안전(ADDITIVE·guarded).
    - limit_per_source: None → LIMITS(소스별 2). int/dict 도 허용.

    build.py 배선(2줄):
        from briefer import extra_sources
        extra_sources.merge_into(today)
    (source.fetch_all() 직후, outline.outline_stories(today['stories']) 직전에 삽입.)
    """
    base = today.get("stories") or []

    # 레이어 (c) 준비: seen-store 로드 + fetch 단계에서 이미 본 후보 스킵.
    store = load_seen() if use_seen_store else {"urls": set(), "heads": set(), "entries": []}
    seen_pred = (lambda u, h: is_seen(store, u, h)) if use_seen_store else None

    raw = fetch_extra(since_days=since_days, limit_per_source=limit_per_source,
                      seen_pred=seen_pred)
    extra = to_stories(raw, start_n=len(base) + 1)

    # 레이어 (b): aiofmodu 당일 5건. 레이어 (a): 방출 목록 내 상호 중복.
    seen_url = {s.get("url") for s in base if s.get("url")}
    seen_h = {_norm_headline(s.get("headline", "")) for s in base}
    added, newly = 0, []
    n = len(base) + 1
    for s in extra:
        hn = _norm_headline(s["headline"])
        # (a)+(b) 당일/aiofmodu 중복  및  (c) fetch 이후 to_stories 에서 새로 생긴 교차일 중복 재확인
        if s["url"] in seen_url or hn in seen_h:
            continue
        if use_seen_store and is_seen(store, s["url"], s["headline"]):
            continue
        s["n"] = f"{n:02d}"  # dedup로 건너뛴 만큼 번호 재정렬(연속 보장)
        base.append(s)
        seen_url.add(s["url"]); seen_h.add(hn)
        newly.append(s)
        n += 1; added += 1

    # 레이어 (c) 영속화: 이번에 방출한 것만 store에 기록 후 저장.
    if use_seen_store and newly:
        for s in newly:
            record_seen(store, s["url"], s["headline"])
        save_seen(store)

    today["stories"] = base
    print(f"[extra:merge_into] aiofmodu {len(base) - added}건 + 추가 {added}건 = "
          f"총 {len(base)}건 (seen-store={seen_store_path()})", file=sys.stderr)
    return today


# ----------------------------------------------------------------------------
# 자체 테스트: python3 -m briefer.extra_sources   (또는 python3 briefer/extra_sources.py)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("========== fetch_extra() 실피드 테스트 ==========", file=sys.stderr)
    raw = fetch_extra(since_days=3, limit_per_source=5)
    bysrc: dict[str, list] = {}
    for a in raw:
        bysrc.setdefault(a["source"], []).append(a)
    print("\n---- 소스별 수집 결과 ----")
    for name in ("MIT Tech Review", "CB Insights", "aibase", "AI타임스"):
        lst = bysrc.get(name, [])
        feed = FEEDS.get(name if name != "aibase" else "aibase")
        print(f"\n[{name}] feed={feed}")
        print(f"  fetched: {len(lst)}건")
        if lst:
            ex = lst[0]
            pub = ex["published"].isoformat() if ex["published"] else "(날짜미상)"
            print(f"  예시: {ex['title'][:80]}")
            print(f"        {ex['url']}  · {pub}")
        else:
            print("  (0건 — 실패/차단/필터결과)")

    print("\n========== to_stories() 한국어화 테스트 (앞 3건) ==========", file=sys.stderr)
    sample = raw[:3]
    stories = to_stories(sample, start_n=6)
    for s in stories:
        print(f"\n{s['n']} {s['emoji']} {s['headline']}")
        print(f"   본문: {s['body']}")
        print(f"   함의: {s['takeaway']}")
        print(f"   URL : {s['url']}")
    if not stories:
        print("\n(한국어 스토리 0건 — OpenRouter 키 없음 또는 요약 실패. 위 stderr 확인)")
