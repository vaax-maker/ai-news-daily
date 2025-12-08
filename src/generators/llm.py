import os
import time
import re
import google.generativeai as genai
from google.api_core import exceptions
import groq as groq_lib
from typing import List

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
    prompt = f"""
아래 {display_name} 관련 기사 내용을 5줄 이내 한국어로 핵심만 요약해줘.
가능하면 수치, 회사명, 핵심 이슈 위주로 하고, 각 줄은 불릿 기호 "□"으로 시작해줘.
핵심 키워드는 강조(**굵게**) 처리하되, URL이나 링크는 포함하지 마.

제목: {title}
내용:
{text[:2000]}
"""
    try:
        return _summarize_with_grok(prompt)
    except Exception as e:
        # print(f"[LLM] Grok failed ({e}), switching to Gemini...")
        return _summarize_with_gemini(prompt)

def rank_items_with_ai(items: List[tuple], limit: int) -> List[tuple]:
    if not items:
        return []

    # Sort by time desc first, take top 60
    candidates = sorted(items, key=lambda x: x[0], reverse=True)[:60]
    
    candidates_text = "\n".join([f"{idx}. {t[1]}" for idx, t in enumerate(candidates)])
    
    prompt = f"""
다음은 다양한 테크 뉴스 기사들의 제목 리스트야.
이 중에서 오늘날짜 뉴스레터에 포함시킬 가장 '중요하고 의미 있는' 기사 {limit}개를 골라줘.

중요도 판단 기준:
1. 주요 기술 기업(OpenAI, Google, Apple 등)의 새로운 제품/모델 출시
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
        # Using summarization function to call LLM
        try:
            resp = _summarize_with_grok(prompt)
        except:
            resp = _summarize_with_gemini(prompt)

        matches = re.findall(r"\d+", resp)
        ranked_indices = [int(m) for m in matches]
        
    except Exception as e:
        print(f"[LLM] Ranking failed ({e}), fallback to time sort.")
        return candidates[:limit]

    selected = []
    seen = set()
    for idx in ranked_indices:
        if idx in seen: continue
        if 0 <= idx < len(candidates):
            selected.append(candidates[idx])
            seen.add(idx)
            
    if len(selected) < limit:
        for idx, item in enumerate(candidates):
            if idx not in seen:
                selected.append(item)
                if len(selected) >= limit: break
                
    return selected[:limit]
