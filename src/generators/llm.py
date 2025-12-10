import os
import time
import re
import google.generativeai as genai
from google.api_core import exceptions
import groq as groq_lib
from typing import List

# Heuristic keyword buckets for lightweight ranking
IMPORTANT_COMPANIES = [
    "openai", "google", "alphabet", "apple", "microsoft", "meta",
    "amazon", "nvidia", "amd", "samsung", "lg", "tesla",
]
EVENT_KEYWORDS = ["모델", "model", "출시", "발표", "release", "launch", "upgrade", "v2", "v3"]
BUSINESS_KEYWORDS = ["인수", "acquisition", "합병", "merger", "m&a", "투자", "ipo", "규제", "policy", "법", "ban"]
NEGATIVE_KEYWORDS = ["튜토리얼", "tutorial", "가이드", "guide", "how to", "홍보", "sponsor", "sponsored"]

# Pre-lowered keyword lists to avoid repeated lower() calls and to catch case variants
EVENT_KEYWORDS_LOWER = [kw.lower() for kw in EVENT_KEYWORDS]
BUSINESS_KEYWORDS_LOWER = [kw.lower() for kw in BUSINESS_KEYWORDS]
NEGATIVE_KEYWORDS_LOWER = [kw.lower() for kw in NEGATIVE_KEYWORDS]

# Groq Client Initialization
try:
    Groq = groq_lib.Groq
except ImportError:
    Groq = None

# Gemini Config
MAX_GEMINI_RETRY_DELAY = 15.0

def _extract_retry_delay(exc: Exception, default: float = 30.0) -> float:
    message = str(exc).lower()
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message)
    if match:
        try:
            return min(float(match.group(1)), MAX_GEMINI_RETRY_DELAY)
        except ValueError:
            pass
    return min(default, MAX_GEMINI_RETRY_DELAY)

def _score_title(title: str) -> int:
    """Lightweight heuristic scoring to reduce LLM usage.

    The goal is to approximate the previous AI ranking intent without
    spending tokens. Scores favor big-tech launches, AI model updates,
    and business moves while demoting tutorials or promotional posts.
    """

    lowered = title.lower()
    score = 0

    # Company mentions carry the biggest weight
    for kw in IMPORTANT_COMPANIES:
        if kw in lowered:
            score += 3

    # Product/model events
    for kw in EVENT_KEYWORDS_LOWER:
        if kw in lowered:
            score += 2

    # Business / policy changes
    for kw in BUSINESS_KEYWORDS_LOWER:
        if kw in lowered:
            score += 2

    # Penalties for low-value/tutorial-like items
    for kw in NEGATIVE_KEYWORDS_LOWER:
        if kw in lowered:
            score -= 2

    return score

def _rank_with_heuristics(items: List[tuple], limit: int) -> List[tuple]:
    scored = []
    for ts, title, *rest in items:
        score = _score_title(title)
        scored.append((score, ts, (ts, title, *rest)))

    # Sort by score desc, then by time desc to keep freshness
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [entry[2] for entry in scored[:limit]]

def _summarize_with_gemini(prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")
    
    last_exc = None
    for attempt in range(3):
        try:
            res = model.generate_content(prompt)
            return res.text.strip()
        except exceptions.ResourceExhausted as exc:
            last_exc = exc
            if attempt == 2: raise
            delay = _extract_retry_delay(exc)
            print(f"[Gemini] Quota exceeded, retrying in {delay}s...")
            time.sleep(delay)
        except exceptions.GoogleAPICallError as exc:
            last_exc = exc
            if attempt == 2: raise
            time.sleep((attempt + 1) * 5)
            
    raise last_exc if last_exc else RuntimeError("Gemini summarization failed")

def _summarize_with_grok(prompt: str) -> str:
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY is not set.")
    
    if not Groq:
        raise ImportError("Groq library not installed properly.")

    client = Groq(api_key=api_key)
    model = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
    
    res = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
    )
    return res.choices[0].message.content.strip()

def summarize_article(text: str, title: str, display_name: str) -> str:
    # Check if any API key is available
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROK_API_KEY"):
        return "API Key 미설정으로 AI 요약 생략"

    prompt = f"""
아래 {display_name} 관련 기사를 "한글"로 요약해줘.
조건:
1. 스타트업 사업가에게 정보도움이 되도록, 기사의 핵심을 육하원칙에 맞게 요약해줘 (2줄)
2. 배경, 관련수치,세부내용을 추가해줘(2줄)
3. 기사내용의 의미와 전망(1줄)
4. 기사의 제목이 영문일 경우 반드시 **한글로 번역**하여 1줄로 요약할 것.
5. 명사형 종결 어미(~함, ~임)으로 끝낼 것.

제목: {title}
내용:
{text[:2000]}
"""
    try:
        return _summarize_with_grok(prompt)
    except Exception as e:
        # print(f"[LLM] Grok failed ({e}), switching to Gemini...")
        return _summarize_with_gemini(prompt)

def _rank_with_llm(candidates: List[tuple], limit: int) -> List[tuple]:
    candidates_text = "\n".join([f"{idx}. {t[1]}" for idx, t in enumerate(candidates)])

    prompt = f"""
다음은 다양한 테크 뉴스 기사들의 제목 리스트야.
이 중에서 오늘날짜 뉴스레터에 포함시킬 가장 '중요하고 의미 있는' 기사 {limit}개를 골라줘.

중요도 판단 기준:
1. 주요 기술 기업(OpenAI, Google, Apple, 삼성, LG 등)의 새로운 제품/모델 출시
2. AI 분야의 획기적인 연구 성과나 논문
3. 업계의 큰 인수합병이나 정책 변화
4. 단순 튜토리얼이나 홍보성 기사는 제외

응답 형식:
- 가장 중요하다고 생각되는 기사의 '인덱스 번호'만 쉼표(,)로 나열해줘.
- 예: 1, 5, 10, 3, 2

[기사 목록]
{candidates_text}
"""

    try:
        try:
            resp = _summarize_with_grok(prompt)
        except Exception:
            resp = _summarize_with_gemini(prompt)

        matches = re.findall(r"\d+", resp)
        ranked_indices = [int(m) for m in matches]

    except Exception as e:
        print(f"[LLM] Ranking failed ({e})")
        return []

    selected = []
    seen = set()
    for idx in ranked_indices:
        if idx in seen:
            continue
        if 0 <= idx < len(candidates):
            selected.append(candidates[idx])
            seen.add(idx)

    if len(selected) < limit:
        for idx, item in enumerate(candidates):
            if idx not in seen:
                selected.append(item)
                if len(selected) >= limit:
                    break

    return selected[:limit]

def rank_items_with_ai(items: List[tuple], limit: int) -> List[tuple]:
    if not items:
        return []

    strategy = os.getenv("AI_RANKING_STRATEGY", "heuristic").lower()
    max_candidates = int(os.getenv("AI_RANKING_CANDIDATES", "40"))

    # Sort by time desc first, take top N
    candidates = sorted(items, key=lambda x: x[0], reverse=True)[:max_candidates]

    # If strategy is not explicitly LLM-based, use heuristics only
    if strategy not in ("llm", "hybrid"):
        return _rank_with_heuristics(candidates, limit)

    llm_available = os.environ.get("GEMINI_API_KEY") or os.environ.get("GROK_API_KEY")
    if not llm_available:
        if strategy == "llm":
            print("[LLM] API Key missing, using heuristic ranking instead.")
        return _rank_with_heuristics(candidates, limit)

    llm_ranked = _rank_with_llm(candidates, limit)

    # If LLM failed or empty, fall back to heuristics
    if not llm_ranked:
        if strategy == "llm":
            print("[LLM] Ranking unavailable, falling back to heuristic scores.")
        return _rank_with_heuristics(candidates, limit)

    # Hybrid keeps LLM order but will top up with heuristic order if needed
    if strategy == "hybrid" and len(llm_ranked) < limit:
        heuristic_fill = _rank_with_heuristics(candidates, limit)
        combined = llm_ranked + [i for i in heuristic_fill if i not in llm_ranked]
        return combined[:limit]

    return llm_ranked[:limit]
