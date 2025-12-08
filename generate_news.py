import os
import time
import datetime
import feedparser
import google.generativeai as genai
from google.api_core import exceptions
import groq as groq_lib
import re
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List
from urllib.parse import urlparse

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover - optional dependency for local dev
    GoogleTranslator = None

if not hasattr(groq_lib, "Groq"):
    raise ImportError(
        "The installed `groq` package does not expose the `Groq` client class. "
        "Install groq>=0.4.2 to enable Groq-based summarization."
    )

Groq = groq_lib.Groq

@dataclass
class CategoryConfig:
    key: str
    display_name: str
    rss_feeds: List[str]
    archive_dir: str
    index_path: str
    max_articles: int = 15
    fallback_image_url: str = ""
    # selection_mode: 기사 선택 방식 설정 (워크플로 입력 → 환경 변수 → 기본값 순으로 결정)
    #  - "time": RSS에서 가져온 최신 순으로 정렬해 상위 N개 선택
    #  - "random": 정렬 없이 무작위 섞기 후 상위 N개 선택
    #  - "keyword": 지정한 키워드가 제목·본문에 들어간 기사만 필터링 후 최신 순으로 선택
    selection_mode: str = "time"
    keyword_filters: List[str] = field(default_factory=list)
    # importance_scoring: LLM을 이용해 기사 중요도를 평가하고 선별할지 여부
    use_ai_ranking: bool = False


# --- 설정 ---


def resolve_selection_mode(key: str, default: str = "time") -> str:
    # <카테고리>_SELECTION_MODE 환경 변수로 선택 모드를 지정한다.
    # 예) AI 카테고리에 랜덤 적용: `export AI_SELECTION_MODE=random`
    # GitHub Actions( daily-news.yml )에서 workflow_dispatch 입력을 이 환경 변수로 전달한다.
    # 지원 값 외가 들어오면 기본값(default)을 사용한다.
    env_val = os.getenv(f"{key.upper()}_SELECTION_MODE", default).strip().lower()
    if env_val in {"time", "random", "keyword"}:
        return env_val
    return default


def resolve_use_ai_ranking(key: str, default: bool = False) -> bool:
    # <카테고리>_USE_AI_RANKING 환경 변수가 "true"면 AI 랭킹을 적용한다.
    env_val = os.getenv(f"{key.upper()}_USE_AI_RANKING", str(default)).lower()
    return env_val == "true"


def resolve_keyword_filters(key: str) -> List[str]:
    # <카테고리>_KEYWORDS 환경 변수에 콤마(,)로 구분된 키워드를 넣는다.
    # 예) AI 카테고리에 "openai"와 "llm"을 필터링: `export AI_KEYWORDS="openai,llm"`
    # daily-news.yml의 workflow_dispatch 입력이 동일 이름의 환경 변수로 채워져 여기에서 읽힌다.
    # 키워드는 대소문자 구분 없이 제목·본문에서 검색된다.
    raw = os.getenv(f"{key.upper()}_KEYWORDS", "").strip()
    if not raw:
        return []
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


# --- 설정 ---
CATEGORIES: Dict[str, CategoryConfig] = {
    "ai": CategoryConfig(
        key="ai",
        display_name="AI",
        rss_feeds=[
            "https://www.aitimes.com/rss/allArticle.xml",
            "https://www.bloter.net/archives/category/ai/feed",
            "https://www.reddit.com/r/ArtificialInteligence/top/.rss?t=day",
            "https://www.techmeme.com/feed.xml",
            # New Feeds
            "https://techcrunch.com/category/artificial-intelligence/feed/",
            "https://a16z.com/feed/",
            "https://www.themiilk.com/feed",
            "https://www.technologyreview.com/feed/",
            "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
            "http://www.aitimes.kr/rss/allArticle.xml",
        ],
        archive_dir="docs/ai/daily",
        index_path="docs/ai/index.html",
        fallback_image_url="https://placehold.co/800x420/111827/FFFFFF?text=AI+News",
        selection_mode=resolve_selection_mode("ai"),
        keyword_filters=resolve_keyword_filters("ai"),
        use_ai_ranking=resolve_use_ai_ranking("ai", default=True),  # Apply AI ranking by default for AI
    ),
    "xr": CategoryConfig(
        key="xr",
        display_name="XR",
        rss_feeds=[
            "https://www.roadtovr.com/feed/",
            "https://uploadvr.com/rss",
            "https://arinsider.co/feed/",
            "https://skarredghost.com/feed/",
        ],
        archive_dir="docs/xr/daily",
        index_path="docs/xr/index.html",
        selection_mode=resolve_selection_mode("xr"),
        keyword_filters=resolve_keyword_filters("xr"),
    ),
}

# Gemini 호출 간격 (무료 플랜이면 6~7초 이상 권장, 유료/여유 있으면 줄여도 됨)
REQUEST_INTERVAL_SECONDS = 2
# Google 측에서 제안하는 retry-after 값이 1분 이상일 때 워크플로가 멈춰 보이는 것을
# 방지하기 위해 지연 시간을 상한 처리한다.
MAX_GEMINI_RETRY_DELAY = 15.0
HIGHLIGHT_COLOR = "#fff6b0"


# **텍스트** → 강조 색상(문구만) + 목록 처리
def markdown_bold_to_highlight(html_text: str) -> str:
    """Convert **bold** markers into highlighted phrases and list items."""

    def wrap_highlight(match):
        text = match.group(1)
        if len(text.split()) >= 2:
            return (
                f"<span class='highlight' style='background-color: {HIGHLIGHT_COLOR};"
                " padding: 3px 5px; border-radius: 4px;'>"
                f"{text}"
                "</span>"
            )
        return f"<strong>{text}</strong>"

    lines = []
    for raw_line in html_text.splitlines():
        cleaned = raw_line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[•□\-]\s*", "", cleaned)
        converted = re.sub(r"\*\*(.+?)\*\*", wrap_highlight, cleaned)
        lines.append(converted)

    if not lines:
        return ""

    items = [f"<li>{line}</li>" for line in lines]
    return "<ul class='summary-list'>" + "".join(items) + "</ul>"


def contains_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))


_translator = None


@lru_cache(maxsize=256)
def translate_title_to_korean(title: str) -> str:
    """Translate English titles to Korean for display. Fallback to original on failure."""

    if not title or contains_korean(title):
        return title

    if GoogleTranslator is None:
        return title

    global _translator
    if _translator is None:
        _translator = GoogleTranslator(source="auto", target="ko")

    try:
        result = _translator.translate(title)
        if result:
            return result
    except Exception:
        pass

    return title


def format_timestamp(ts: float) -> str:
    if not ts:
        return "발행 시각 정보 없음"

    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "발행 시각 정보 없음"


def extract_source_name(entry, link: str) -> str:
    source_title = getattr(entry, "source", None)
    if source_title:
        title_val = getattr(source_title, "title", None)
        if title_val:
            return title_val

    netloc = urlparse(link or "").netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or "출처 미상"


def extract_image_url(entry) -> str:
    media_content = getattr(entry, "media_content", None) or []
    if media_content:
        first = media_content[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]

    media_thumbnail = getattr(entry, "media_thumbnail", None) or []
    if media_thumbnail:
        thumb = media_thumbnail[0]
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]

    image_link = getattr(entry, "image", None)
    if isinstance(image_link, dict) and image_link.get("href"):
        return image_link["href"]

    def extract_from_html(html_text: str) -> str:
        if not html_text:
            return ""
        match = re.search(r"<img[^>]+src=['\"]([^'\"]+)['\"]", html_text, re.IGNORECASE)
        return match.group(1) if match else ""

    contents = getattr(entry, "content", None) or []
    for content in contents:
        if isinstance(content, dict):
            candidate = extract_from_html(content.get("value", ""))
        else:
            candidate = extract_from_html(getattr(content, "value", ""))
        if candidate:
            return candidate

    summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
    html_candidate = extract_from_html(summary_html)
    if html_candidate:
        return html_candidate

    return ""


def sanitize_summary(summary: str) -> str:
    cleaned_lines = []
    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "URL:" in stripped:
            continue
        if re.search(r"출처\s*:", stripped):
            continue
        if re.search(r"https?://", stripped):
            continue
        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines)


def _extract_retry_delay(exc: Exception, default: float = 30.0) -> float:
    """Extract retry-after seconds from Gemini quota errors."""

    message = str(exc).lower()
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message)
    if match:
        try:
            return min(float(match.group(1)), MAX_GEMINI_RETRY_DELAY)
        except ValueError:
            pass

    return min(default, MAX_GEMINI_RETRY_DELAY)


# 1) Gemini/Grok 요약 함수
def _build_summary_prompt(text: str, title: str, display_name: str) -> str:
    return f"""
아래 {display_name} 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로 하고, 각 줄은 불릿 기호 "□"으로 시작해줘.
핵심 키워드는 강조(**굵게**) 처리하되, URL이나 링크는 포함하지 마.

제목: {title}
내용:
{text[:2000]}
"""


def _summarize_with_gemini(prompt: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    # 사용 중인 모델 (필요시 다른 ID로 교체)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            res = model.generate_content(prompt)
            return res.text.strip()
        except exceptions.ResourceExhausted as exc:
            last_exc = exc
            if attempt == 2:
                raise

            delay = _extract_retry_delay(exc)
            print(
                f"[warn] Gemini quota exceeded, retrying in {delay:.1f}s "
                f"(attempt {attempt + 2}/3)"
            )
            time.sleep(delay)
        except exceptions.GoogleAPICallError as exc:
            last_exc = exc
            if attempt == 2:
                raise

            backoff = (attempt + 1) * 5
            print(
                f"[warn] Gemini API error ({exc}); retrying in {backoff}s "
                f"(attempt {attempt + 2}/3)"
            )
            time.sleep(backoff)

    raise last_exc if last_exc else RuntimeError("Gemini summarization failed")


def _summarize_with_grok(prompt: str) -> str:
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY is not set for Grok fallback")

    client = Groq(api_key=api_key)
    model = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")

    res = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
    )

    content = res.choices[0].message.content if res.choices else ""
    if not content:
        raise RuntimeError("Grok did not return a summary")

    return content.strip()


def summarize(text: str, title: str, display_name: str) -> str:
    prompt = _build_summary_prompt(text, title, display_name)

    try:
        return _summarize_with_grok(prompt)
    except Exception as grok_exc:
        print(f"[warn] Grok failed with error: {grok_exc}; falling back to Gemini")

        try:
            return _summarize_with_gemini(prompt)
        except Exception as gemini_exc:
            raise RuntimeError(
                "Both Grok and Gemini summarization failed. Check API keys and quotas."
            ) from gemini_exc





# 1.5) AI 중요도 평가 (Ranking)
def _build_ranking_prompt(items_for_ranking: List[tuple], limit: int) -> str:
    # (idx, title) 목록 생성
    candidates = []
    for idx, (ts, title, link, content, entry) in enumerate(items_for_ranking):
        candidates.append(f"{idx}. {title}")
    
    candidates_text = "\n".join(candidates)

    return f"""
다음은 다양한 AI/테크 뉴스 기사들의 제목 리스트야.
이 중에서 오늘날짜 뉴스레터에 포함시킬 가장 '중요하고 의미 있는' 기사 {limit}개를 골라줘.

중요도 판단 기준:
1. 주요 기술 기업(OpenAI, Google, Apple 등)의 새로운 제품/모델 출시
2. AI 분야의 획기적인 연구 성과나 논문
3. 업계의 큰 인수합병이나 정책 변화
4. 단순 튜토리얼이나 홍보성 기사는 제외

응답 형식:
- 가장 중요하다고 생각되는 기사의 '인덱스 번호'를 중요도 순서대로 나열해줘.
- 번호 외에 다른 설명은 필요 없어.
- 쉼표(,)로 구분해줘. 예: 1, 5, 10, 3, 2

[기사 목록]
{candidates_text}
"""

def rank_items_with_ai(raw_items: List[tuple], limit: int) -> List[tuple]:
    """
    LLM을 사용하여 기사들의 중요도를 평가하고 상위 limit개를 반환한다.
    - 비용 절약을 위해 raw_items가 너무 많으면 최신 50개 정도로 먼저 자르고 보낸다.
    """
    if not raw_items:
        return []

    # API 비용 고려: 최신순 정렬 후 최대 60개만 LLM에게 평가 요청 (그 이상은 토큰/비용 낭비 가능성)
    candidates = sorted(raw_items, key=lambda x: x[0], reverse=True)[:60]
    
    prompt = _build_ranking_prompt(candidates, limit)
    
    ranked_indices = []
    try:
        # 요약과 동일한 Grok -> Gemini 로직 사용
        response_text = _summarize_with_grok(prompt)
        # 응답 파싱 (숫자만 추출)
        # 예: "1, 5, 23" -> [1, 5, 23]
        matches = re.findall(r"\d+", response_text)
        ranked_indices = [int(m) for m in matches]
        
    except Exception as e:
        print(f"[warn] AI ranking failed ({e}); falling back to time-based sorting.")
        return candidates[:limit]

    # 선택된 인덱스에 해당하는 항목 추출 (중복 제거 및 순서 유지)
    selected_items = []
    seen_indices = set()
    
    # LLM이 반환한 순서대로 담기
    for idx in ranked_indices:
        if idx in seen_indices:
            continue
        if 0 <= idx < len(candidates):
            selected_items.append(candidates[idx])
            seen_indices.add(idx)
            
    # 만약 LLM이 충분한 개수를 반환하지 않았다면, 원본 순서(최신순)대로 나머지 채움
    if len(selected_items) < limit:
        for idx in range(len(candidates)):
            if idx not in seen_indices:
                selected_items.append(candidates[idx])
                if len(selected_items) >= limit:
                    break
                    
    return selected_items[:limit]


# 2) RSS → (여러 RSS 전체) → 시간/랜덤/AI 정렬 → 상위 N개만 요약
def fetch_and_summarize(config: CategoryConfig):
    raw_items = []

    for feed_url in config.rss_feeds:
        d = feedparser.parse(feed_url)

        for entry in d.entries:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            content = getattr(entry, "summary", "") or getattr(
                entry, "description", ""
            )

            # 게시 시각(published) 또는 수정 시각(updated) 사용
            published = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )
            if published:
                ts = time.mktime(published)  # epoch time
            else:
                ts = 0  # 날짜 정보 없으면 가장 뒤로 밀림 (time 모드일 때)

            raw_items.append((ts, title, link, content, entry))

    keywords = [kw.lower() for kw in config.keyword_filters]

    if config.selection_mode == "keyword" and keywords:
        # 키워드 모드: 제목+본문에 키워드가 하나라도 포함된 기사만 남긴다.
        # 키워드는 resolve_keyword_filters()로 환경 변수에서 읽어온 리스트를 사용한다.
        raw_items = [
            item
            for item in raw_items
            if any(kw in ((item[1] or "") + " " + (item[3] or "")).lower() for kw in keywords)
        ]

    candidate_items = []
    
    # [설정] 최신 2일(오늘, 어제) 기사만 필터링
    # 48시간 기준보다는 '날짜' 기준으로 하는 것이 일반적이나, 편의상 최근 48시간 + 여유분으로 처리하거나
    # datetime 비교를 수행. 여기서는 간단히 timestamp 기준으로 48시간 이내만 1차 필터링 수행.
    # 단, published 정보가 없는(ts=0) 경우는 제외되거나(또는 포함하거나) 정책 결정 필요.
    # 여기서는 ts >= (현재 - 2일) 인 것만 남김.
    two_days_ago = time.time() - 48 * 60 * 60
    
    # 1차 필터링: 최근 2일 데이터를 우선 확보
    filtered_items = [item for item in raw_items if item[0] >= two_days_ago]
    
    # 만약 필터링 결과가 너무 적으면(5개 미만) 그냥 전체에서 가져오거나, 그대로 진행.
    # 여기서는 그대로 진행.
    raw_items = filtered_items

    # 기사 정렬/선택 방식
    three_days_ago = time.time() - 3 * 24 * 60 * 60
    if config.selection_mode == "time":
        # 시간 모드: 게시 시각(ts) 내림차순으로 최신 기사부터 정렬
        raw_items.sort(key=lambda x: x[0], reverse=True)
    elif config.selection_mode == "random":
        # 랜덤 모드: 최근 3일 내 기사만 대상으로 무작위 섞기 (없으면 전체 사용)
        recent_items = [item for item in raw_items if item[0] and item[0] >= three_days_ago]
        candidate_items = recent_items if recent_items else raw_items
        random.shuffle(candidate_items)
        raw_items = candidate_items
    elif config.selection_mode == "keyword":
        # 키워드 모드: 필터링 후 최신 순 정렬 (키워드가 없으면 아래 else로 동일 처리)
        raw_items.sort(key=lambda x: x[0], reverse=True)
    else:
        raw_items.sort(key=lambda x: x[0], reverse=True)

    # ---------------------------------------------------------
    # AI 랭킹 적용 여부 확인
    # ---------------------------------------------------------
    # selection_mode가 'random'이 아니고, config에 use_ai_ranking가 켜져 있으면
    # 기존 정렬 결과에서 AI가 다시 선별한다.
    if config.use_ai_ranking and config.selection_mode != "random":
        print(f"[{config.key.upper()}] Applying AI Ranking for selection...")
        selected = rank_items_with_ai(raw_items, config.max_articles)
    else:
        # 상위 N개만 선택 (기존 방식)
        selected = raw_items[: config.max_articles]

    summarized = []
    for idx, (ts, title, link, content, entry) in enumerate(selected):
        text_with_url = content + f"\n\n기사 URL: {link}"

        summary = summarize(text_with_url, title, config.display_name)
        summary = sanitize_summary(summary)
        
        # [변경] fallback_image_url 사용 안 함. 이미지가 없으면 빈 문자열.
        real_image_url = extract_image_url(entry)
        image_url = real_image_url if real_image_url else ""

        summarized.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published_display": format_timestamp(ts),
                "source_name": extract_source_name(entry, link),
                "image_url": image_url,
            }
        )

        # 쿼터 보호용 딜레이
        time.sleep(REQUEST_INTERVAL_SECONDS)

    return summarized


# 3) 개별 실행(날짜+시간) 페이지 생성
def build_daily_page(articles, date_str: str, time_str: str, config: CategoryConfig) -> str:
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>{config.display_name} News - {date_str} {time_str}</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    # [Bug Fix] Missing <style> tag start
    parts.append("  <style>")
    parts.append(
        "    body { font-family: Roboto, 'Noto Sans KR', 'Pretendard', sans-serif; line-height: 1.5; margin: 0; background: #fff; color: #111; }"
    )
    parts.append("    a { text-decoration: none; color: inherit; }")
    parts.append("    .container { max-width: 1000px; margin: 0 auto; padding: 20px; }")
    parts.append("    h1 { font-size: 1.5rem; margin-bottom: 5px; color: #111; letter-spacing: -1px; }")
    parts.append("    .meta { color: #888; font-size: 0.9rem; margin-bottom: 20px; }")
    
    # [변경] GNB 스타일 (Home | AI | XR | Archive)
    parts.append("    header { background: #f4f4f4; border-bottom: 1px solid #ddd; padding: 10px 0; margin-bottom: 30px; }")
    parts.append("    .gnb { max-width: 1000px; margin: 0 auto; display: flex; gap: 20px; padding: 0 20px; }")
    parts.append("    .gnb a { font-weight: bold; color: #555; text-decoration: none; font-size: 1rem; }")
    parts.append("    .gnb a:hover { color: #2272c9; }")
    parts.append("    .gnb a.active { color: #2272c9; }")

    parts.append("    .board-list { border-top: 2px solid #2272c9; }")
    parts.append(
        "    .list-item { display: block; border-bottom: 1px solid #e0e0e0; padding: 15px 10px; transition: background 0.2s; }"
    )
    parts.append("    .list-item:hover { background: #f9f9f9; }")
    
    # [변경] 제목 폰트 키움 (1.1rem -> 1.35rem)
    parts.append("    .item-title { font-size: 1.35rem; font-weight: normal; margin: 0 0 8px; line-height: 1.4; letter-spacing: -0.5px; }")
    parts.append("    .item-title a { color: #232f3e; transition: color 0.2s; }")
    parts.append("    .item-title a:hover { color: #d43f3a; text-decoration: underline; }")
    
    parts.append(
        "    .item-meta { font-size: 0.85rem; color: #959595; display: flex; gap: 8px; align-items: center; margin-top: 4px; }"
    )
    parts.append("    .source-badge { color: #2272c9; font-weight: bold; }")
    parts.append("    .original-title { color: #aaa; font-size: 0.8rem; display: block; margin-top: 2px; }")

    parts.append("    .item-body { margin-top: 10px; display: flex; gap: 15px; }")
    parts.append(
        "    .summary-text { flex: 1; font-size: 0.95rem; color: #333; line-height: 1.6; word-break: break-all; }"
    )
    parts.append("    .summary-list { margin: 0; padding-left: 1.2rem; }")
    parts.append("    .summary-list li { margin-bottom: 3px; }")
    
    # [변경] 이미지 크기 및 배치 조정
    parts.append(
        "    .item-image { width: 160px; height: 110px; object-fit: cover; border-radius: 4px; border: 1px solid #eee; flex-shrink: 0; }"
    )
    
    parts.append(
        "    .highlight { background-color: #fff8c4; padding: 2px 4px; border-radius: 2px; }"
    )
    
    parts.append("    @media (max-width: 600px) {")
    parts.append("      .container { padding: 15px; }")
    # [변경] 모바일에서 이미지는 숨기거나 작게 -> 작게 유지
    parts.append("      .item-image { width: 90px; height: 70px; }")
    parts.append("      .item-title { font-size: 1.2rem; }")
    parts.append("    }")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    # [변경] 공통 GNB 추가
    parts.append("  <header>")
    parts.append("    <div class='gnb'>")
    parts.append("      <a href='../../index.html'>Home</a>")
    parts.append("      <a href='../../ai/index.html' " + ("class='active'" if config.key == 'ai' else "") + ">AI News</a>")
    parts.append("      <a href='../../xr/index.html' " + ("class='active'" if config.key == 'xr' else "") + ">XR News</a>")
    parts.append("    </div>")
    parts.append("  </header>")

    parts.append("  <div class='container'>")
    # [삭제] 기존 .nav 제거
    parts.append(f"    <h1>{date_str} {config.display_name} News</h1>")
    parts.append(f"    <p class='meta'>Updated at {time_str} (KST)</p>")
    parts.append("    <div class='board-list'>")

    for art in articles:
        summary_html = markdown_bold_to_highlight(art["summary"])
        display_title = translate_title_to_korean(art["title"])
        original_hint = (
            f"<span class='original-title'>원문 제목: {art['title']}</span>"
            if display_title != art["title"]
            else ""
        )

        parts.append("      <div class='list-item'>")
        parts.append(
            "        <div class='item-title'>"
            f"<a href='{art['link']}' target='_blank'>{display_title}</a>"
        )
        if original_hint:
             parts.append(f"          <br/>{original_hint}")
        parts.append("        </div>")

        meta_bits = [bit for bit in [art.get("source_name"), art.get("published_display")] if bit]
        if meta_bits:
            parts.append("        <div class='item-meta'>")
            parts.append(f"          <span class='source-badge'>{meta_bits[0]}</span>")
            if len(meta_bits) > 1:
                parts.append(f"          <span>| {meta_bits[1]}</span>")
            parts.append("        </div>")

        if summary_html or art.get("image_url"):
            parts.append("        <div class='item-body'>")
            
            # [변경] 이미지가 있을 때만 <img> 태그 생성
            if art.get("image_url"):
                parts.append(
                     f"          <a href='{art['link']}' target='_blank'><img src='{art['image_url']}' alt='썸네일' class='item-image' loading='lazy'/></a>"
                )

            parts.append("          <div class='summary-text'>")
            if summary_html:
                parts.append(f"            {summary_html}")
            parts.append("          </div>")
            parts.append("        </div>")
            
        parts.append("      </div>")

    parts.append("    </div>") # End board-list
    parts.append("  </div>") # End container
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# 4) index.html 목록 페이지 재생성 (여러 번/하루 여러 회 실행 포함)
def collect_run_entries(config: CategoryConfig):
    os.makedirs(config.archive_dir, exist_ok=True)

    files = [f for f in os.listdir(config.archive_dir) if f.endswith(".html")]

    run_entries = []
    for fname in files:
        base = fname.replace(".html", "")
        date_str = base
        time_str = ""

        if "_" in base:
            date_part, time_part = base.split("_", 1)
            date_str = date_part
            if len(time_part) >= 6:
                hh = time_part[0:2]
                mm = time_part[2:4]
                ss = time_part[4:6]
                time_str = f"{hh}:{mm}:{ss}"
            else:
                time_str = time_part
        run_entries.append((base, date_str, time_str, fname))

    run_entries.sort(key=lambda x: x[0], reverse=True)
    return run_entries


def rebuild_index_html(config: CategoryConfig):
    run_entries = collect_run_entries(config)

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append(f"  <title>Daily {config.display_name} News Archive</title>")
    parts.append(
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
    )
    parts.append("  <style>")
    parts.append(
        "    body { font-family: Roboto, 'Noto Sans KR', 'Pretendard', sans-serif; margin: 0; line-height: 1.6; background: #fff; color: #111; }"
    )
    parts.append("    a { text-decoration: none; color: inherit; }")
    parts.append("    .container { max-width: 1000px; margin: 0 auto; padding: 20px; }")
    
    
    parts.append("    h1 { margin-bottom: 0.35rem; font-size: 1.5rem; letter-spacing: -1px; }")
    # [변경] GNB 스타일 (Index 페이지용)
    parts.append("    header { background: #f4f4f4; border-bottom: 1px solid #ddd; padding: 10px 0; margin-bottom: 30px; }")
    parts.append("    .gnb { max-width: 1000px; margin: 0 auto; display: flex; gap: 20px; padding: 0 20px; }")
    parts.append("    .gnb a { font-weight: bold; color: #555; text-decoration: none; font-size: 1rem; }")
    parts.append("    .gnb a:hover { color: #2272c9; }")

    parts.append("    .run-list { list-style: none; padding: 0; border-top: 2px solid #2272c9; margin-top: 15px; }")
    parts.append(
        "    .run-item { border-bottom: 1px solid #e0e0e0; padding: 12px 10px; transition: background 0.2s; }"
    )
    parts.append("    .run-item:hover { background: #f9f9f9; }")
    
    parts.append(
        "    .run-item a { color: #232f3e; font-size: 1.1rem; }"
    )
    parts.append("    .run-item a:hover { color: #d43f3a; text-decoration: underline; }")
    parts.append(
        "    .timestamp { color: #888; font-size: 0.85rem; display: block; margin-top: 4px; }"
    )
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    # [변경] GNB 추가 (카테고리별 아카이브 페이지)
    parts.append("  <header>")
    parts.append("    <div class='gnb'>")
    parts.append("      <a href='../index.html'>Home</a>")
    parts.append("      <a href='index.html' class='active'>" + config.display_name + " News</a>")
    parts.append("    </div>")
    parts.append("  </header>")
    parts.append("  <div class='container'>")
    parts.append(f"    <h1>Daily {config.display_name} News Archive</h1>")
    parts.append(
        f"  <p>실행 시점(날짜+시간, KST)별로 저장된 {config.display_name} 기사 요약 목록입니다.</p>"
    )

    if not run_entries:
        parts.append("  <p>아직 저장된 뉴스가 없습니다.</p>")
    else:
        parts.append("  <ul class='run-list'>")
        for base, date_str, time_str, fname in run_entries:
            if time_str:
                label = f"{date_str} {time_str}" # [변경] 라벨 간소화
            else:
                label = f"{date_str} {config.display_name} News"
            parts.append(
                "    <li class='run-item'>"
                f"<a href='daily/{fname}'>{label}</a>"
                f"<span class='timestamp'>원본 생성 시간: {date_str} {time_str or ''} (KST)</span>"
                "</li>"
            )
        parts.append("  </ul>")

    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    os.makedirs(os.path.dirname(config.index_path), exist_ok=True)
    with open(config.index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def build_root_index(categories: Dict[str, CategoryConfig]):
    categorized_runs = {cfg.key: collect_run_entries(cfg) for cfg in categories.values()}

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='ko'>")
    parts.append("<head>")
    parts.append("  <meta charset='utf-8' />")
    parts.append("  <title>AI & XR News Archives</title>")
    parts.append("  <meta name='viewport' content='width=device-width, initial-scale=1' />")
    parts.append("  <style>")
    parts.append(
        "    body { font-family: Roboto, 'Noto Sans KR', 'Pretendard', sans-serif; margin: 0; line-height: 1.6; background: #fff; color: #111; }"
    )
    parts.append("    a { text-decoration: none; color: inherit; }")
    parts.append("    a { text-decoration: none; color: inherit; }")
    parts.append("    .container { max-width: 1000px; margin: 0 auto; padding: 20px; }")
    # [변경] GNB 스타일
    parts.append("    header { background: #f4f4f4; border-bottom: 1px solid #ddd; padding: 10px 0; margin-bottom: 30px; }")
    parts.append("    .gnb { max-width: 1000px; margin: 0 auto; display: flex; gap: 20px; padding: 0 20px; }")
    parts.append("    .gnb a { font-weight: bold; color: #555; text-decoration: none; font-size: 1rem; }")
    parts.append("    .gnb a:hover { color: #2272c9; }")
    parts.append("    .gnb a.active { color: #2272c9; }")

    parts.append("    h1 { margin-bottom: 0.5rem; letter-spacing: -1px; }")
    parts.append("    .subtitle { color: #555; margin-bottom: 20px; font-size: 0.95rem; }")
    
    parts.append("    .tabs { display: flex; gap: 5px; margin-bottom: 15px; border-bottom: 2px solid #2272c9; }")
    parts.append(
        "    .tab-btn { padding: 10px 20px; border: 1px solid #ddd; border-bottom: none; border-radius: 5px 5px 0 0; background: #f9f9f9; cursor: pointer; font-weight: bold; color: #555; margin-bottom: -2px; z-index: 1; }"
    )
    parts.append(
        "    .tab-btn.active { background: #2272c9; color: #fff; border-color: #2272c9; }"
    )
    
    parts.append("    .tab-panel { display: none; padding-top: 10px; }")
    parts.append("    .tab-panel.active { display: block; }")
    
    parts.append("    .panel-card { background: #fff; }")
    parts.append("    .list-header { border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 10px; font-weight: bold; }")

    parts.append("    ul { list-style: none; padding: 0; }")
    parts.append("    li { border-bottom: 1px solid #eee; padding: 8px 5px; font-size: 1rem; }")
    parts.append("    li:hover { background: #f9f9f9; }")
    
    parts.append("    .timestamp { color: #888; font-size: 0.85rem; margin-left: 8px; }")
    parts.append("    .archive-link { margin-bottom: 15px; font-weight: bold; }")
    parts.append("    .archive-link a { color: #2272c9; text-decoration: underline; }")
    parts.append("  </style>")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <header>")
    parts.append("    <div class='gnb'>")
    parts.append("      <a href='index.html' class='active'>Home</a>")
    parts.append("      <a href='ai/index.html'>AI News</a>")
    parts.append("      <a href='xr/index.html'>XR News</a>")
    parts.append("    </div>")
    parts.append("  </header>")
    parts.append("  <div class='container'>")
    parts.append("    <h1>AI & XR Daily News Archives</h1>")
    parts.append("    <p class='subtitle'>탭을 눌러 AI/XR 뉴스를 구분해 확인하세요. 모든 시각은 한국 표준시(KST) 기준이며, 과거 실행 결과도 누적해 보여줍니다.</p>")

    parts.append("  <div class='tabs'>")
    for cfg in categories.values():
        parts.append(
            f"    <button class='tab-btn' data-target='{cfg.key}'>{cfg.display_name} 뉴스</button>"
        )
    parts.append("  </div>")

    for cfg in categories.values():
        runs = categorized_runs.get(cfg.key, [])
        parts.append(
            f"  <div class='tab-panel' id='{cfg.key}'>"
        )
        parts.append("    <div class='panel-card'>")
        parts.append(
            f"      <p class='archive-link'><a href='{cfg.key}/index.html'>{cfg.display_name} 아카이브 전체 보기 →</a></p>"
        )

        if not runs:
            parts.append("      <p>아직 저장된 뉴스가 없습니다.</p>")
        else:
            parts.append("      <ul>")
            for base, date_str, time_str, fname in runs:
                label = f"{date_str} {time_str} KST" if time_str else f"{date_str} KST"
                parts.append(
                    "        <li>"
                    f"<a href='{cfg.key}/daily/{fname}'>{cfg.display_name} 뉴스</a>"
                    f" <span class='timestamp'>{label}</span>"
                    "</li>"
                )
            parts.append("      </ul>")

        parts.append("    </div>")
        parts.append("  </div>")

    parts.append("  <script>")
    parts.append(
        "    const tabs = document.querySelectorAll('.tab-btn'); const panels = document.querySelectorAll('.tab-panel');"
    )
    parts.append(
        "    function activateTab(key) { panels.forEach(p => p.classList.toggle('active', p.id === key)); tabs.forEach(t => t.classList.toggle('active', t.dataset.target === key)); }"
    )
    parts.append(
        "    tabs.forEach(btn => btn.addEventListener('click', () => activateTab(btn.dataset.target)));"
    )
    parts.append("    if (tabs.length) { activateTab(tabs[0].dataset.target); }")
    parts.append("  </script>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# 5) main 실행 함수
def main():
    # GitHub Actions는 UTC이므로, UTC + 9시간 = KST
    now_utc = datetime.datetime.utcnow()
    now = now_utc + datetime.timedelta(hours=9)

    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 파일 이름용 ID (YYYY-MM-DD_HHMMSS, KST 기준)
    run_id = now.strftime("%Y-%m-%d_%H%M%S")

    for cfg in CATEGORIES.values():
        articles = fetch_and_summarize(cfg)
        daily_html = build_daily_page(articles, date_str, time_str, cfg)

        os.makedirs(cfg.archive_dir, exist_ok=True)
        daily_path = os.path.join(cfg.archive_dir, f"{run_id}.html")

        # 매 실행마다 새로운 파일 생성
        with open(daily_path, "w", encoding="utf-8") as f:
            f.write(daily_html)

        rebuild_index_html(cfg)

    build_root_index(CATEGORIES)


if __name__ == "__main__":
    main()
