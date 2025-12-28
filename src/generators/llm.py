import os
import time
import re
import random
import google.generativeai as genai
from google.api_core import exceptions
import groq as groq_lib
from typing import List
from src.utils.usage_logger import log_api_usage

# ============================================================================
# Rate Limiting Configuration (Free Tier Optimization)
# ============================================================================
# Groq Free Tier: 30 requests/minute, 14,400 requests/day
# Gemini Free Tier: 15 requests/minute, 1,500 requests/day
# 
# Strategy:
# 1. Add delay between API calls to stay under rate limits
# 2. Exponential backoff on rate limit errors
# 3. Jitter to avoid thundering herd
# ============================================================================

# Minimum delay between API calls (seconds)
MIN_REQUEST_DELAY = float(os.getenv("LLM_REQUEST_DELAY", "2.0"))

# Maximum retry attempts
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Base delay for exponential backoff (seconds)
BASE_BACKOFF_DELAY = 5.0

# Last request timestamp for rate limiting
_last_api_call_time = 0.0

def _rate_limit_delay():
    """Enforce minimum delay between API calls."""
    global _last_api_call_time
    now = time.time()
    elapsed = now - _last_api_call_time
    if elapsed < MIN_REQUEST_DELAY:
        sleep_time = MIN_REQUEST_DELAY - elapsed + random.uniform(0.1, 0.5)  # Add jitter
        time.sleep(sleep_time)
    _last_api_call_time = time.time()

def _is_rate_limit_error(error_msg: str) -> bool:
    """Check if error is a rate limit error."""
    rate_limit_indicators = [
        "rate limit", "rate_limit", "quota", "exceeded", 
        "too many requests", "429", "resource exhausted",
        "requests per minute", "rpm"
    ]
    error_lower = error_msg.lower()
    return any(indicator in error_lower for indicator in rate_limit_indicators)

def _extract_retry_delay(exc: Exception, default: float = 30.0) -> float:
    """Extract retry delay from error message or use default."""
    message = str(exc).lower()
    # Try to find "retry in Xs" or "retry after Xs" pattern
    match = re.search(r"retry (?:in|after) ([0-9]+(?:\.[0-9]+)?)\s*s", message)
    if match:
        try:
            return min(float(match.group(1)), 60.0)  # Cap at 60 seconds
        except ValueError:
            pass
    # Try to find just a number of seconds mentioned
    match = re.search(r"(\d+)\s*seconds?", message)
    if match:
        try:
            return min(float(match.group(1)), 60.0)
        except ValueError:
            pass
    return min(default, 30.0)

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
    """Call Gemini API with rate limiting and retry logic."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    
    genai.configure(api_key=key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)
    
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            # Apply rate limiting
            _rate_limit_delay()
            
            res = model.generate_content(prompt)
            
            # Usage Tracking
            try:
                if hasattr(res, 'usage_metadata'):
                    in_tok = res.usage_metadata.prompt_token_count
                    out_tok = res.usage_metadata.candidates_token_count
                    log_api_usage("gemini", model_name, in_tok, out_tok, context="summary")
            except Exception as e:
                print(f"[Gemini] Usage tracking failed: {e}")

            return res.text.strip()
            
        except exceptions.ResourceExhausted as exc:
            last_exc = exc
            if attempt == MAX_RETRIES - 1: 
                raise
            delay = _extract_retry_delay(exc)
            print(f"[Gemini] Quota exceeded (attempt {attempt+1}/{MAX_RETRIES}), waiting {delay}s...")
            time.sleep(delay)
            
        except exceptions.GoogleAPICallError as exc:
            last_exc = exc
            error_msg = str(exc)
            
            if _is_rate_limit_error(error_msg):
                if attempt == MAX_RETRIES - 1:
                    raise
                # Exponential backoff for rate limits
                delay = BASE_BACKOFF_DELAY * (2 ** attempt) + random.uniform(0, 2)
                print(f"[Gemini] Rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {delay:.1f}s...")
                time.sleep(delay)
            else:
                if attempt == MAX_RETRIES - 1:
                    raise
                # Linear backoff for other errors
                delay = (attempt + 1) * 5
                print(f"[Gemini] API error (attempt {attempt+1}/{MAX_RETRIES}): {error_msg[:50]}...")
                time.sleep(delay)
                
        except Exception as exc:
            last_exc = exc
            if attempt == MAX_RETRIES - 1:
                raise
            delay = (attempt + 1) * 3
            print(f"[Gemini] Unexpected error (attempt {attempt+1}/{MAX_RETRIES}): {str(exc)[:50]}...")
            time.sleep(delay)
            
    raise last_exc if last_exc else RuntimeError("Gemini summarization failed")

def _summarize_with_grok(prompt: str) -> str:
    """Call Grok/Groq API with rate limiting and retry logic."""
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY is not set.")
    
    if not Groq:
        raise ImportError("Groq library not installed properly.")

    client = Groq(api_key=api_key, base_url="https://api.groq.com")
    model = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
    
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            # Apply rate limiting
            _rate_limit_delay()
            
            res = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
            
            # Usage Tracking
            try:
                if hasattr(res, 'usage'):
                    in_tok = res.usage.prompt_tokens
                    out_tok = res.usage.completion_tokens
                    log_api_usage("grok", model, in_tok, out_tok, context="summary")
            except Exception as e:
                print(f"[Grok] Usage tracking failed: {e}")

            return res.choices[0].message.content.strip()
            
        except Exception as exc:
            last_exc = exc
            error_msg = str(exc)
            
            if _is_rate_limit_error(error_msg):
                if attempt == MAX_RETRIES - 1:
                    raise
                # Exponential backoff for rate limits
                delay = BASE_BACKOFF_DELAY * (2 ** attempt) + random.uniform(0, 2)
                print(f"[Grok] Rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {delay:.1f}s...")
                time.sleep(delay)
            else:
                if attempt == MAX_RETRIES - 1:
                    raise
                # Linear backoff for other errors
                delay = (attempt + 1) * 3
                print(f"[Grok] API error (attempt {attempt+1}/{MAX_RETRIES}): {error_msg[:50]}...")
                time.sleep(delay)
    
    raise last_exc if last_exc else RuntimeError("Grok summarization failed")

def summarize_article(text: str, title: str, display_name: str) -> str:
    """Summarize an article using LLM with fallback and rate limiting."""
    # Check if any API key is available
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROK_API_KEY"):
        return "API Key 미설정으로 AI 요약 생략"

    # === 상세 구조화 프롬프트 (XML 태그 기반, Gemini 최적화) ===
    prompt = f"""<task>
뉴스 기사를 섹션별로 구조화된 상세 요약으로 작성
</task>

<output_format>
## 1. 핵심 내용
**주제**: 한 문장으로 핵심 요약

- 세부 내용 1 (구체적 수치/금액/일정 포함)
- 세부 내용 2
- 세부 내용 3

## 2. 배경 및 맥락
- 왜 이런 결정/사건이 발생했는지
- 관련 기술/시장 상황 설명

## 3. 주요 관계자/기업
- 관련 기업/인물과 역할

## 4. 전략적 의미
- 산업/시장에 미치는 영향
- 경쟁 구도 변화

## 5. 향후 전망
- 예상되는 후속 영향
- 리스크 요인

**한 줄 요약**: (기사의 핵심을 한 문장으로)
</output_format>

<constraint>
- 각 섹션에 2-4개의 bullet point 포함
- 수치(금액, 날짜, 비율)는 반드시 명시
- 문장 끝은 ~함, ~임, ~됨 형식
- 전체 분량 400-600자
- 불필요한 섹션은 생략 가능
</constraint>

<example>
## 1. 핵심 내용
**주제**: 엔비디아가 그록과 200억달러(약 29조원) 규모 기술 라이선스 계약 체결

- 그록의 LPU(언어처리유닛) 관련 지적재산권을 비독점 라이선스로 확보함
- 창립자 조나단 로스, 사장 써니 마드라 등 핵심 인재가 엔비디아로 합류함
- 그록클라우드 사업 제외한 대부분의 자산이 계약 대상임

## 2. 배경 및 맥락
- 그록의 LPU는 LLM 추론에서 GPU 대비 최대 5배 빠른 속도와 저지연 성능 보유함
- AI 서비스에서 추론(Inference) 경쟁력이 학습만큼 중요해지는 추세임

## 3. 주요 관계자/기업
- 그록: 독립 기업 유지, 신임 CEO 사이먼 에드워즈가 경영권 승계
- 엔비디아: 젠슨 황 CEO가 LPU를 AI 팩토리 아키텍처에 통합 계획 발표

## 4. 전략적 의미
- 전체 인수가 아닌 라이선스+인재영입 방식으로 반독점 규제 리스크 회피함
- GPU 중심 생태계에서 실시간 추론 시장까지 영역 확장하는 전략임

## 5. 향후 전망
- LPU와 GPU 결합으로 AI 서비스 실시간성과 에너지 효율 대폭 개선 전망됨
- 구글, AWS 등 빅테크의 자체 칩 개발 경쟁이 변수로 남음

**한 줄 요약**: 엔비디아가 추론 특화 칩(LPU) 기술과 핵심 인재를 29조원에 확보, AI 학습을 넘어 실시간 추론 시장까지 지배력 확대를 노림
</example>

<verification>
응답 전 확인:
- 모든 섹션에 구체적 내용이 있는가?
- 수치/금액/일정이 포함되었는가?
- 한 줄 요약이 있는가?
</verification>

<article>
제목: {title}

{text[:2500]}
</article>

위 기사를 구조화된 형식으로 요약하세요.
"""

    # Try Gemini first (한글 형식 준수 우수), then Grok as fallback
    gemini_error = None
    grok_error = None
    
    try:
        return _summarize_with_gemini(prompt)
    except Exception as e:
        gemini_error = str(e)
        print(f"[Gemini] Failed: {gemini_error[:100]}")
    
    try:
        return _summarize_with_grok(prompt)
    except Exception as e:
        grok_error = str(e)
        print(f"[Grok] Failed: {grok_error[:100]}")
    
    # Both failed - return error message instead of raising
    error_summary = f"Gemini: {gemini_error[:50] if gemini_error else 'N/A'}, Grok: {grok_error[:50] if grok_error else 'N/A'}"
    print(f"[LLM] Both APIs failed - {error_summary}")
    raise RuntimeError(f"All LLM providers failed: {error_summary}")

def analyze_text_with_llm(prompt: str) -> str:
    """Generic wrapper to try Grok then Gemini for analysis tasks."""
    try:
        try:
            return _summarize_with_grok(prompt)
        except Exception:
            return _summarize_with_gemini(prompt)
    except Exception as e:
        print(f"[LLM] Analysis failed: {e}")
        return ""


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
