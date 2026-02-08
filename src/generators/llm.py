import os
import time
import re
import random
import google.generativeai as genai
from google.api_core import exceptions
import groq as groq_lib
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
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

# Gemini API key rotation index
_gemini_key_index = 0
_gemini_api_keys = []

def _get_gemini_api_keys():
    """Parse and return list of Gemini API keys from environment."""
    global _gemini_api_keys
    if not _gemini_api_keys:
        keys_str = os.environ.get("GEMINI_API_KEY", "")
        if keys_str:
            # Split by comma and strip whitespace
            _gemini_api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return _gemini_api_keys

def _get_next_gemini_key():
    """Get next Gemini API key in round-robin fashion."""
    global _gemini_key_index
    keys = _get_gemini_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    
    key = keys[_gemini_key_index % len(keys)]
    _gemini_key_index += 1
    
    if len(keys) > 1:
        print(f"[Gemini] Using API key #{(_gemini_key_index - 1) % len(keys) + 1}/{len(keys)}")
    
    return key

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
    # Global Tech Giants
    "openai", "google", "alphabet", "apple", "microsoft", "meta",
    "amazon", "nvidia", "amd", "samsung", "lg", "tesla",
    # AI-focused companies
    "anthropic", "xai", "perplexity", "huggingface", "stability ai",
    "mistral", "deepseek", "cohere", "inflection", "character.ai",
    # Korean Tech
    "네이버", "카카오", "sk텔레콤", "kt", "삼성전자", "lg전자", "현대차",
]

# AI Models & Products (high relevance)
AI_MODELS = [
    "gpt", "chatgpt", "gemini", "claude", "grok", "sora", "midjourney",
    "stable diffusion", "dall-e", "하이퍼클로바", "hyperclova",
    "copilot", "cursor", "vision pro", "quest", "hololens",
]

EVENT_KEYWORDS = ["모델", "model", "출시", "발표", "release", "launch", "upgrade", "v2", "v3"]
BUSINESS_KEYWORDS = ["인수", "acquisition", "합병", "merger", "m&a", "투자", "ipo", "규제", "policy", "법", "ban"]

# Negative keywords - expanded to filter irrelevant news
NEGATIVE_KEYWORDS = [
    # Tutorial/Promo
    "튜토리얼", "tutorial", "가이드", "guide", "how to", "홍보", "sponsor", "sponsored",
    # Local/Regional news (not AI-related)
    "여수", "나주", "광주시", "전남", "경남", "충북", "충남", "강원", 
    "마을", "빈집", "철거", "주차장", "텃밭", "추경", "진료버스",
    # Irrelevant sectors
    "농식품부", "농촌", "농업", "과수", "축산", "어업", "수산", "조달청",
    "보건복지", "환경부", "국토부", "해양수산",
    # Entertainment/Politics (unless AI-related context)
    "연예", "아이돌", "드라마", "예능",
]

# Pre-lowered keyword lists to avoid repeated lower() calls and to catch case variants
EVENT_KEYWORDS_LOWER = [kw.lower() for kw in EVENT_KEYWORDS]
BUSINESS_KEYWORDS_LOWER = [kw.lower() for kw in BUSINESS_KEYWORDS]
NEGATIVE_KEYWORDS_LOWER = [kw.lower() for kw in NEGATIVE_KEYWORDS]
AI_MODELS_LOWER = [kw.lower() for kw in AI_MODELS]

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
            break  # Count once per title

    # AI Model mentions (high relevance)
    for kw in AI_MODELS_LOWER:
        if kw in lowered:
            score += 3
            break  # Count once per title

    # Product/model events
    for kw in EVENT_KEYWORDS_LOWER:
        if kw in lowered:
            score += 2
            break

    # Business / policy changes
    for kw in BUSINESS_KEYWORDS_LOWER:
        if kw in lowered:
            score += 2
            break

    # Penalties for low-value/tutorial-like items (강화된 페널티)
    for kw in NEGATIVE_KEYWORDS_LOWER:
        if kw in lowered:
            score -= 5  # 강화된 페널티로 비관련 기사 확실히 제외

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
    # Get next API key in rotation
    key = _get_next_gemini_key()
    
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

def _summarize_with_openai(prompt: str) -> str:
    """Call OpenAI API (GPT-5.2) with rate limiting and retry logic."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI library not installed.")
    
    client = openai.OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-5.2")
    
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            # Apply rate limiting
            _rate_limit_delay()
            
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,
                temperature=0.3
            )
            
            # Usage Tracking
            try:
                if hasattr(res, 'usage'):
                    in_tok = res.usage.prompt_tokens
                    out_tok = res.usage.completion_tokens
                    log_api_usage("openai", model, in_tok, out_tok, context="summary")
            except Exception as e:
                print(f"[OpenAI] Usage tracking failed: {e}")
            
            return res.choices[0].message.content.strip()
            
        except Exception as exc:
            last_exc = exc
            error_msg = str(exc)
            
            if _is_rate_limit_error(error_msg):
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = BASE_BACKOFF_DELAY * (2 ** attempt) + random.uniform(0, 2)
                print(f"[OpenAI] Rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {delay:.1f}s...")
                time.sleep(delay)
            else:
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = (attempt + 1) * 3
                print(f"[OpenAI] API error (attempt {attempt+1}/{MAX_RETRIES}): {error_msg[:50]}...")
                time.sleep(delay)
    
    raise last_exc if last_exc else RuntimeError("OpenAI summarization failed")


def _summarize_with_grok(prompt: str) -> str:
    """Call Grok/Groq API with rate limiting and retry logic."""
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY is not set.")
    
    if not Groq:
        raise ImportError("Groq library not installed properly.")

    # Temporarily unset OPENAI_BASE_URL to prevent Groq library from using wrong endpoint
    openai_base_url = os.environ.pop("OPENAI_BASE_URL", None)
    openai_api_base = os.environ.pop("OPENAI_API_BASE", None)
    
    try:
        client = Groq(api_key=api_key)
    finally:
        # Restore environment variables if they existed
        if openai_base_url is not None:
            os.environ["OPENAI_BASE_URL"] = openai_base_url
        if openai_api_base is not None:
            os.environ["OPENAI_API_BASE"] = openai_api_base
    model = os.getenv("GROK_MODEL", "qwen/qwen3-32b")
    
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

def _parse_summary_response(response: str, original_title: str) -> dict:
    """Parse LLM response to extract title and summary."""
    # Remove any <think> tags
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    
    # Extract title
    title_match = re.search(r'\*\*제목\*\*:\s*(.+?)(?:\n|$)', response)
    new_title = title_match.group(1).strip() if title_match else original_title
    
    # Remove title line from summary
    summary = re.sub(r'\*\*제목\*\*:\s*.+?\n', '', response, count=1).strip()
    
    # Ensure title doesn't end with '...'
    if new_title.endswith('...'):
        new_title = new_title.rstrip('.') + '.'
    
    # Fallback to original if new title is empty or too short
    if len(new_title) < 10:
        new_title = original_title
    
    return {
        "title": new_title,
        "summary": summary
    }


def summarize_article(text: str, title: str, display_name: str) -> dict:
    """Summarize an article using LLM with fallback and rate limiting.
    
    Returns:
        dict with 'title' (완성된 제목) and 'summary' (요약 HTML)
    """
    # Check if any API key is available
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROK_API_KEY"):
        return {"title": title, "summary": "API Key 미설정으로 AI 요약 생략"}

    # === 개선된 프롬프트: 제목 생성 + 자기완결적 요약 ===
    prompt = f"""<task>
뉴스 기사를 요약하고, 완전한 제목을 생성하세요.
요약만 읽어도 기사의 맥락을 완전히 파악할 수 있어야 합니다.
</task>

<output_format>
**제목**: (기사 핵심을 담은 완전한 한 문장 제목, 50자 이내)

## 1. 핵심 내용
**주제**: 한 문장으로 핵심 요약 (누가/무엇을/왜 했는지 포함)

- 세부 내용 1 (구체적 수치/금액/일정 포함)
- 세부 내용 2
- 세부 내용 3

## 2. 배경 및 맥락
- 이 사건이 발생하게 된 업계 상황이나 이유
- 관련 기술/시장의 현재 트렌드

## 3. 시장 영향 및 의미
- 이 발표/사건이 왜 중요한지
- 업계/소비자에게 미치는 영향

**한 줄 요약**: (기사의 핵심을 한 문장으로, 맥락 포함)
</output_format>

<constraint>
★ 핵심 원칙: 요약만 읽어도 원문 없이 기사를 완전히 이해할 수 있어야 함 ★

1. **제목 규칙**: 
   - 반드시 완전한 문장으로 끝날 것 ('...'으로 끝나면 안 됨)
   - 핵심 키워드와 수치 포함
   - 50자 이내

2. **자기완결적 요약 규칙**:
   - 5W1H 포함: 누가(Who), 무엇을(What), 왜(Why), 언제(When), 어디서(Where), 어떻게(How)
   - 약어나 전문용어 사용 시 간단한 설명 병기 (예: "LPU(언어처리유닛)")
   - 숫자/금액에는 비교 맥락 추가 (예: "200억달러(전년 대비 30% 증가)")
   - "이것", "해당", "그" 같은 지시어 사용 금지 → 구체적 명칭 사용

3. **문체 규칙**:
   - 각 섹션에 2-3개의 bullet point
   - 문장 끝은 ~함, ~임, ~됨 형식
   - **중요 키워드나 핵심 수치(2-3단어)는 **bold** 처리**
   - 전체 분량 600-800자

4. **품질 검증**:
   - 요약을 읽은 독자가 "그래서 뭐?"라고 묻지 않도록 의미/영향 반드시 포함
   - 불필요한 섹션은 생략 가능하되, "왜 중요한지"는 반드시 포함
</constraint>

<example>
**제목**: 엔비디아, 그록 LPU 기술 200억달러에 라이선스 계약 체결

## 1. 핵심 내용
**주제**: **엔비디아**가 AI 추론 전문기업 **그록**의 LPU(언어처리유닛) 기술을 **200억달러**(약 29조원)에 라이선스 계약 체결함

- 그록의 LPU 관련 지적재산권을 비독점 라이선스로 확보함
- 창립자 조나단 로스, 사장 써니 마드라 등 **핵심 인재**가 엔비디아로 합류함
- 그록클라우드 사업 제외한 대부분의 자산이 계약 대상임

## 2. 배경 및 맥락
- 그록의 LPU는 LLM 추론에서 GPU 대비 **최대 5배** 빠른 속도와 저지연 성능 보유함
- AI 서비스에서 추론(Inference) 경쟁력이 학습만큼 중요해지는 추세임

## 3. 시장 영향 및 의미
- 전체 인수가 아닌 라이선스+인재영입 방식으로 **반독점 규제 리스크** 회피함
- GPU 중심 생태계에서 **실시간 추론 시장**(연 40% 성장)까지 영역 확장하는 전략임

**한 줄 요약**: 엔비디아가 추론 특화 칩(LPU) 기술과 핵심 인재를 29조원에 확보, AI 학습을 넘어 실시간 추론 시장까지 지배력 확대를 노림
</example>

<article>
원본 제목: {title}

{text[:1500]}
</article>

위 기사에 대해 완전한 제목과 자기완결적 구조화 요약을 작성하세요.
"""

    # Try OpenAI (GPT-5.2) first, then Grok, then Gemini as fallback
    openai_error = None
    grok_error = None
    gemini_error = None
    
    raw_response = None
    
    # 1st: OpenAI GPT-5.2
    try:
        raw_response = _summarize_with_openai(prompt)
    except Exception as e:
        openai_error = str(e)
        print(f"[OpenAI] Failed: {openai_error[:100]}")
    
    # 2nd: Groq
    if raw_response is None:
        try:
            raw_response = _summarize_with_grok(prompt)
        except Exception as e:
            grok_error = str(e)
            print(f"[Grok] Failed: {grok_error[:100]}")
    
    # 3rd: Gemini
    if raw_response is None:
        try:
            raw_response = _summarize_with_gemini(prompt)
        except Exception as e:
            gemini_error = str(e)
            print(f"[Gemini] Failed: {gemini_error[:100]}")
    
    # If we got a response, parse it
    if raw_response:
        return _parse_summary_response(raw_response, title)
    
    # All failed - return error message instead of raising
    error_summary = f"OpenAI: {openai_error[:30] if openai_error else 'N/A'}, Grok: {grok_error[:30] if grok_error else 'N/A'}, Gemini: {gemini_error[:30] if gemini_error else 'N/A'}"
    print(f"[LLM] All APIs failed - {error_summary}")
    raise RuntimeError(f"All LLM providers failed: {error_summary}")

def analyze_text_with_llm(prompt: str) -> str:
    """Generic wrapper to try OpenAI, then Grok, then Gemini for analysis tasks."""
    try:
        try:
            return _summarize_with_openai(prompt)
        except Exception:
            try:
                return _summarize_with_grok(prompt)
            except Exception:
                return _summarize_with_gemini(prompt)
    except Exception as e:
        print(f"[LLM] Analysis failed: {e}")
        return ""


def _rank_with_llm(candidates: List[tuple], limit: int) -> List[tuple]:
    candidates_text = "\n".join([f"{idx}. {t[1]}" for idx, t in enumerate(candidates)])

    prompt = f"""다음 기사 제목 중 AI/XR 뉴스레터에 포함할 {limit}개를 선정하세요.

[✅ 포함해야 할 기사]
1. 주요 AI/XR 기업의 신제품/업데이트 (OpenAI, Google, Meta, Nvidia, Anthropic 등)
2. AI 모델 출시/업그레이드 (GPT, Gemini, Claude, Sora, Grok 등)
3. 대규모 투자/인수합병 소식 (금액이 명시된 경우 우선)
4. 업계 트렌드를 보여주는 분석/전망 기사
5. 글로벌 시장에 영향을 미치는 정책/규제 변화
6. 한국 주요 기업(네이버, 카카오, 삼성, LG)의 AI 관련 뉴스

[❌ 반드시 제외해야 할 기사]
1. 특정 지역(여수, 나주, 광주 등) 로컬 뉴스 - AI 키워드가 있어도 제외
2. 농업, 수산, 축산, 환경 등 비관련 분야
3. 조달청, 보건복지부 등 AI와 직접 관련 없는 정부 발표
4. 튜토리얼, 가이드, 홍보성 콘텐츠
5. 연예인/정치인 관련 비기술 뉴스
6. 철거, 진료, 마을, 빈집 등 일상 뉴스

[기사 목록]
{candidates_text}

중요도 높은 순서대로 {limit}개의 인덱스 번호만 쉼표로 나열:"""

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


def generate_key_message(ai_articles: list, xr_articles: list) -> str:
    """
    Generate a hooking 3-line Key Message summary for the daily briefing.
    (Legacy function - for backward compatibility, calls the unified function)
    
    Args:
        ai_articles: List of AI article dicts with 'title' key
        xr_articles: List of XR article dicts with 'title' key
        
    Returns:
        HTML formatted bullet list Key Message
    """
    result = generate_key_message_and_keywords(ai_articles, xr_articles)
    return result["key_message"]


def generate_key_message_and_keywords(ai_articles: list, xr_articles: list) -> dict:
    """
    Generate Key Message AND wordcloud keywords in a single LLM call.
    
    Args:
        ai_articles: List of AI article dicts with 'title' key
        xr_articles: List of XR article dicts with 'title' key
        
    Returns:
        dict with:
            - key_message: HTML formatted bullet list
            - keywords: list of (word, category) tuples for wordcloud
    """
    import re
    
    # Collect top titles
    ai_titles = [art.get("title", "") for art in ai_articles[:5]]
    xr_titles = [art.get("title", "") for art in xr_articles[:3]]
    
    all_titles = "\n".join([f"- {t}" for t in ai_titles + xr_titles if t])
    
    fallback_result = {
        "key_message": "<ul><li>오늘의 AI/XR 뉴스를 확인하세요!</li></ul>",
        "keywords": []
    }
    
    if not all_titles:
        return fallback_result
    
    prompt = f"""다음은 오늘의 AI/XR 뉴스 기사 제목 목록입니다.

[작업 1] Key Message 생성 - 생각을 자극하는 인사이트 질문
- 오늘 뉴스를 바탕으로 **독자가 깊이 생각해볼 화두**를 던지는 질문 **정확히 2개** 작성
- 단순 팩트 나열이 아니라, "그래서 이게 왜 중요한가?"에 답하는 인사이트 제공
- 형식: 질문 또는 도발적 명제 (물음표로 끝나거나, 강한 주장)
- 문장 속 **핵심 키워드 1~2개**를 <em> 태그로 감싸서 강조
- 한글로 작성, 이모지 금지, 각 줄 60자 이내

[좋은 예시]
- "<em>AI</em>가 단편영화를 만든다면, 감독의 역할은 무엇이 될까?"
- "<em>엔비디아</em> 29조 베팅 - 추론 시장이 학습 시장을 넘어설 것인가?"
- "VR 피트니스가 헬스장을 대체할 수 있을까? <em>Meta</em>의 도전"
- "<em>OpenAI</em>와 <em>Google</em>의 격차가 좁혀지고 있다 - 승자는 누구?"

[나쁜 예시 - 피할 것]
- "젠슨황 967조 투자 발표" (단순 팩트 나열)
- "AI 영상 기술 발전" (너무 일반적)
- "오늘의 AI 뉴스를 확인하세요" (의미 없음)

[작업 2] 워드클라우드 키워드 추출
- 기사에서 중요한 키워드 30~40개 추출 (최대한 다양하게)
- 각 키워드의 카테고리 지정: Person(인물), Tech(기술), Company(기업/기관), Solution(솔루션/제품)
- 형식: 키워드|카테고리

[기사 목록]
{all_titles}

[출력 형식 - 아래 형식 정확히 따르기]
KEY_MESSAGE:
<em>키워드</em>가 포함된 인사이트 질문 또는 화두 1
<em>키워드</em>가 포함된 인사이트 질문 또는 화두 2

KEYWORDS:
엔비디아|Company
피지컬AI|Tech
젠슨황|Person
... (30개 이상)

출력:"""

    try:
        response = analyze_text_with_llm(prompt)
        if response:
            # Remove any <think> tags and their content
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            
            # Robust REGEX parsing
            # Search for KEY_MESSAGE section
            key_msg_match = re.search(r'(?:KEY_MESSAGE|KEY MESSAGE|Key Message)[:：](.*?)(?:KEYWORDS|KEYWORDS|Keywords)[:：]', response, re.DOTALL | re.IGNORECASE)
            
            # Search for KEYWORDS section (until end of string)
            keywords_match = re.search(r'(?:KEYWORDS|KEYWORDS|Keywords)[:：](.*)', response, re.DOTALL | re.IGNORECASE)
            
            key_message_html = fallback_result["key_message"]
            keywords_list = []

            # 1. Parse Key Message
            if key_msg_match:
                key_message_part = key_msg_match.group(1).strip()
            elif "KEY_MESSAGE:" in response:
                 # Fallback to split if regex fails but keyword exists (simple split)
                 parts = response.split("KEY_MESSAGE:")
                 if len(parts) > 1:
                     # Take until next keyword or end
                     temp = parts[1].split("KEYWORDS:")[0]
                     key_message_part = temp.strip()
                 else:
                     key_message_part = ""
            else:
                key_message_part = ""

            if key_message_part:
                lines = [line.strip() for line in key_message_part.split("\n") if line.strip() and not line.strip().startswith("KEY_MESSAGE")][:2]
                # Remove dashes or bullets if present
                clean_lines = []
                for line in lines:
                    line = re.sub(r'^[-*•]\s*', '', line)
                    clean_lines.append(line)
                
                if clean_lines:
                    li_items = "\n".join([f"<li>{line}</li>" for line in clean_lines])
                    key_message_html = f"<ul>\n{li_items}\n</ul>"
            
            # 2. Parse Keywords
            keywords_part = ""
            if keywords_match:
                keywords_part = keywords_match.group(1).strip()
            elif "KEYWORDS:" in response:
                parts = response.split("KEYWORDS:")
                if len(parts) > 1:
                    keywords_part = parts[1].strip()

            if keywords_part:
                for line in keywords_part.split("\n"):
                    line = line.strip()
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 2:
                            word = parts[0].strip()
                            category = parts[1].strip()
                            # Strip markdown bold/italic
                            word = re.sub(r'[*_]', '', word)
                            category = re.sub(r'[*_]', '', category)
                            
                            if word and category in ["Person", "Tech", "Company", "Solution"]:
                                keywords_list.append((word, category))
            
            return {
                "key_message": key_message_html,
                "keywords": keywords_list[:40]
            }
            
    except Exception as e:
        print(f"[KeyMessage+Keywords] Generation failed: {e}")
    
    return fallback_result
