# [Design] url-analyzer

> 작성일: 2026-02-22
> 단계: Design
> 버전: v1
> 참조: [url-analyzer.plan.md](../../01-plan/features/url-analyzer.plan.md)

---

## 1. 설계 개요

`src/url_analyzer.py`를 `src/parser/` 모듈 기반으로 리팩토링하여 중복 코드를 제거하고,
FastAPI 서버는 독립 도구로 유지하며 CLI 스크립트를 추가한다.

### 변경 대상 파일

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/parser/base.py` | 수정 | `parse_with_fallback()` 추가 |
| `src/url_analyzer.py` | 리팩토링 | 파서 디스패치 방식으로 전환 |
| `scripts/analyze_url.py` | 신규 | CLI 단독 실행 도구 |

---

## 2. P0 — Parser 인터페이스 표준화

### 2-1. `ParsedContent` 스키마 (변경 없음)

현재 스키마가 모든 필드를 포함하고 있어 추가 변경 불필요.

```python
@dataclass
class ParsedContent:
    title: str
    source: str
    date: Optional[str]
    content: str
    keywords: List[str]
    related_links: List[str]
```

### 2-2. `BaseParser` — `parse_with_fallback()` 추가

**위치**: `src/parser/base.py`

```python
class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, url: str) -> bool: ...

    @abstractmethod
    def parse(self, url: str) -> ParsedContent: ...

    def parse_with_fallback(self, url: str, fallback_content: str = "") -> ParsedContent:
        """예외 발생 시 빈 ParsedContent 반환."""
        try:
            return self.parse(url)
        except Exception as e:
            return ParsedContent(
                title=url,
                source=url,
                date=None,
                content=fallback_content or f"[Parse error: {e}]",
                keywords=[],
                related_links=[],
            )
```

**설계 이유**: 호출자가 예외를 직접 처리하지 않아도 항상 `ParsedContent`를 받을 수 있도록
안전망 제공. `analyze_url()` 등에서 try/except 중복 방지.

---

## 3. P1 — `src/url_analyzer.py` 리팩토링

### 3-1. 제거할 함수 (파서로 위임)

| 제거 대상 | 위임 대상 |
|----------|----------|
| `is_youtube_url(url)` | `YouTubeParser.can_parse(url)` |
| `extract_video_id(url)` | `YouTubeParser._extract_video_id(url)` |
| `fetch_youtube_transcript(video_id)` | `YouTubeParser._get_transcript(video_id)` |
| `fetch_article(url)` | `ArticleParser.parse(url)` |

### 3-2. `ParserRegistry` 클래스 추가

**위치**: `src/url_analyzer.py` 상단 (app 선언 이전)

```python
from src.parser.youtube import YouTubeParser
from src.parser.article import ArticleParser
from src.parser.base import ParsedContent

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
_registry.register(ArticleParser())  # fallback: always can_parse=True
```

**설계 이유**: 파서 순서가 중요 — `YouTubeParser`를 먼저 등록해야 YouTube URL이 우선 처리됨.
`ArticleParser.can_parse()`는 항상 `True`이므로 마지막 fallback.

### 3-3. `analyze_url()` 리팩토링

```python
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
```

**변경 전 vs 변경 후**:
- 변경 전: 150줄 (중복 로직, 독자 구현)
- 변경 후: `analyze_url()` 7줄 + `ParserRegistry` 15줄 = 22줄

### 3-4. 유지할 코드

```python
# 유지 대상
app = FastAPI(...)          # FastAPI 앱 인스턴스
AnalyzeRequest              # Pydantic 요청 모델
render_bento_html()         # HTML 렌더링 (P3에서 교체 검토)

@app.post("/analyze")       # JSON 분석 API
@app.get("/bento")          # HTML 반환 API
```

### 3-5. import 정리

```python
# 제거
from youtube_transcript_api import YouTubeTranscriptApi  # 파서로 이동
from bs4 import BeautifulSoup                            # 파서로 이동

# 유지
from __future__ import annotations
import re                    # render_bento_html에서 사용 가능
from typing import List, Optional
import requests              # 필요 시 유지 (parser 내부 처리로 제거 가능)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# 추가
from src.parser.base import BaseParser, ParsedContent
from src.parser.youtube import YouTubeParser
from src.parser.article import ArticleParser
```

**주의**: `src.parser.*` import는 `requirements-extra.txt`에 의존하므로,
메인 파이프라인에서 직접 import되지 않도록 주의. `url_analyzer.py` 자체가
`requirements-extra.txt` 전용이므로 try/except 불필요.

---

## 4. P2 — Quickview 연동 (선택적)

### 4-1. `scripts/analyze_url.py` CLI 도구

```python
#!/usr/bin/env python3
"""CLI: URL을 분석하여 ParsedContent를 출력."""
import sys
import json
from src.url_analyzer import analyze_url

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_url.py <url>")
        sys.exit(1)
    url = sys.argv[1]
    result = analyze_url(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

### 4-2. `process_manual_articles.py` 연동 포인트

현재 `scrape_article_content(url)` 함수가 독자적으로 requests + BeautifulSoup를 사용.

**P2 연동 방안** (선택적 — 이번 사이클 구현 여부 미결):
```python
# scripts/process_manual_articles.py 변경 사항 (선택)
try:
    from src.url_analyzer import analyze_url as _analyze
    def scrape_article_content(url: str) -> dict:
        return _analyze(url)
except ImportError:
    # requirements-extra.txt 미설치 환경에서는 기존 로직 유지
    ...
```

**판단 기준**: `process_manual_articles.py`가 CI 파이프라인에 포함되지 않으므로
`requirements-extra.txt` 의존성 추가가 안전하다. 단, 메인 `requirements.txt`는 변경하지 않음.

---

## 5. P3 — FastAPI 서버 정리

### 5-1. 모듈 docstring 추가

```python
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
```

### 5-2. `render_bento_html()` 유지 결정

Quickview 템플릿(`src/generators/quickview.py`) 연동은 별도 사이클에서 처리.
이번 P3에서는 docstring 추가만 수행.

---

## 6. 구현 순서

```
P0: src/parser/base.py — parse_with_fallback() 추가 (5줄)
    ↓
P1: src/url_analyzer.py — ParserRegistry + analyze_url() 리팩토링
    - 중복 함수 4개 제거
    - ParserRegistry 클래스 추가
    - analyze_url() 재작성
    - import 정리
    ↓
P2: scripts/analyze_url.py — CLI 도구 신규 작성 (15줄)
    ↓
P3: src/url_analyzer.py — 모듈 docstring 추가 (10줄)
```

---

## 7. 검증 기준

| 항목 | 검증 명령 | 기대 결과 |
|------|----------|----------|
| P0 import | `python3 -c "from src.parser.base import BaseParser, ParsedContent; print('OK')"` | OK |
| P1 함수 제거 확인 | `grep -n "def is_youtube_url\|def extract_video_id\|def fetch_article\|def fetch_youtube" src/url_analyzer.py` | 출력 없음 |
| P1 분석 동작 | `python3 -c "from src.url_analyzer import analyze_url; r=analyze_url('https://example.com'); print(r['title'])"` | 제목 출력 |
| P2 CLI | `python3 scripts/analyze_url.py https://example.com` | JSON 출력 |
| P3 docstring | `python3 -c "import src.url_analyzer; print(src.url_analyzer.__doc__[:30])"` | "URL Analyzer" |

---

## 8. 비범위

- `render_bento_html()` → Quickview 템플릿 연동 (다음 사이클)
- `YouTubeParser` 한국어 자막 우선 로직 개선 (`_get_transcript` 현재 `['ko', 'en']` 순서로 충분)
- LLM 요약 연동 (plan 문서의 비범위와 동일)
- Firestore 저장 통합
