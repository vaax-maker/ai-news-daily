# [Plan] url-analyzer

> 작성일: 2026-02-22
> 단계: Plan
> 버전: v1

---

## 1. 배경 및 목적

### 현재 상태

`src/url_analyzer.py`와 `src/parser/` 모듈이 **별개로** 존재하며 중복 구현되어 있음:

| 파일 | 구현 방식 | 문제 |
|------|----------|------|
| `src/url_analyzer.py` | 독립 함수 + FastAPI 앱 | `src/parser/` 미사용, 중복 로직 |
| `src/parser/base.py` | BaseParser ABC + ParsedContent | url_analyzer에서 미호출 |
| `src/parser/youtube.py` | YouTubeParser (OOP) | 실제 파이프라인에 미통합 |
| `src/parser/article.py` | ArticleParser (OOP) | 실제 파이프라인에 미통합 |

### 목표

1. `src/url_analyzer.py`를 `src/parser/` 모듈 기반으로 리팩토링
2. FastAPI 서버를 독립 도구로 정리 (main 파이프라인과 분리 유지)
3. **Quickview 기능과 연동** — URL 수동 등록 시 url-analyzer 활용
4. 중복 코드 제거, `ParsedContent` 표준 출력 형식 통일

---

## 2. 현황 분석

### `src/url_analyzer.py` 중복 구현 목록

| 함수 | 중복 대상 | 처리 방향 |
|------|----------|----------|
| `is_youtube_url()` | YouTubeParser.can_parse() | 제거 → 위임 |
| `extract_video_id()` | YouTubeParser._extract_video_id() | 제거 → 위임 |
| `fetch_youtube_transcript()` | YouTubeParser._get_transcript() | 제거 → 위임 |
| `fetch_article()` | ArticleParser.parse() | 제거 → 위임 |
| `analyze_url()` | 두 파서의 parse() 조합 | 리팩토링 (파서 디스패치) |
| `render_bento_html()` | src/generators/html.py | 별도 quickview 뷰로 이전 검토 |

### FastAPI 엔드포인트 (유지 대상)

```
POST /analyze  — URL 분석 (JSON 반환)
GET  /bento    — URL 분석 후 Bento Grid HTML 반환
```

→ 독립 실행 도구로 유지. main.py와 직접 통합하지 않음.

---

## 3. 작업 범위 (P0~P3)

### P0 — Parser 인터페이스 표준화 (선행)

- `ParsedContent` 스키마 확정 및 누락 필드 추가
- `BaseParser`에 `parse_with_fallback()` 공통 메서드 추가
- `YouTubeParser` 한국어 자막 우선 로직 보완

### P1 — url_analyzer.py 리팩토링

- `analyze_url()` → `YouTubeParser`/`ArticleParser` 디스패치로 교체
- 중복 함수(`is_youtube_url`, `extract_video_id`, `fetch_article` 등) 제거
- `ParserRegistry` 패턴으로 파서 선택 로직 중앙화

### P2 — Quickview 연동 (선택적)

- `process_manual_articles()` 워크플로우에서 url-analyzer 호출
- `scripts/analyze_url.py` — CLI 단독 실행 도구 작성
- 분석 결과 → `generate_quickview_from_parsed()` 함수로 Quickview 페이지 생성

### P3 — FastAPI 서버 정리

- `render_bento_html()` → Quickview 템플릿 활용으로 교체
- 의존성 명확화: `requirements-extra.txt`에서만 사용
- `README` 또는 docstring에 서버 실행 방법 문서화

---

## 4. 우선순위

| 우선순위 | 작업 | 이유 |
|---------|------|------|
| P0 (필수) | parser 표준화 | 이후 작업의 기반 |
| P1 (필수) | url_analyzer 리팩토링 | 중복 제거, 코드 품질 |
| P2 (선택) | Quickview 연동 | 비즈니스 가치, 의존성 있음 |
| P3 (선택) | FastAPI 정리 | 문서화 수준 작업 |

---

## 5. 기술 제약

- `src/url_analyzer.py`는 `requirements-extra.txt` 의존 (fastapi, pydantic, youtube-transcript-api)
- main 파이프라인은 이 의존성 없이 동작해야 함 → **import는 항상 try/except로 감싸기**
- Python 3.11 호환 (`list[dict]` 타입 힌트 사용 가능)
- `YouTubeTranscriptApi`의 `get_transcript` 호출은 `getattr` 패턴 유지 (mypy 회피)

---

## 6. 비범위 (이번 사이클 제외)

- LLM 요약 기능 통합 (url_analyzer → LLM 파이프라인 연결)
- YouTube 자막 없을 때 AI 영상 설명 생성
- 실시간 URL 모니터링/큐 시스템

---

## 7. 예상 소요

| Phase | 예상 시간 |
|-------|---------|
| P0 parser 표준화 | 30분 |
| P1 url_analyzer 리팩토링 | 1시간 |
| P2 Quickview 연동 | 1.5시간 |
| P3 FastAPI 정리 | 30분 |
| **합계** | **3.5시간** |

---

## 8. 검증 방법

```bash
# P0 검증
python3 -c "from src.parser.base import BaseParser, ParsedContent; print('OK')"

# P1 검증
python3 -c "from src.url_analyzer import analyze_url; print(analyze_url('https://example.com'))"

# P2 검증
python3 scripts/analyze_url.py https://example.com

# P3 검증 (FastAPI 서버 실행)
python3 -m uvicorn src.url_analyzer:app --reload
# curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"url": "https://example.com"}'
```
