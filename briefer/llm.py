#!/usr/bin/env python3
"""공통 OpenRouter LLM 클라이언트 — 3개 발행 파이프라인(뉴스·피드백·유튜브) 통일 기반.

텍스트 chat/completions 단일 진입점. 모델 폴백 사슬·재시도·JSON 추출 포함.
키: 환경변수 OPENROUTER_API_KEY, 없으면 ~/xbot/.env 에서 로드(값은 로그에 남기지 않음).
2026-08-18 신설(재구성 원칙1: LLM을 OpenRouter로 통일).
"""
import json
import os
import re
import sys
import time
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"


def _load_key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.expanduser("~/xbot/.env"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


KEY = _load_key()

# 기본 모델 + 폴백 사슬(앞에서부터). 뉴스 파이프라인이 매일 쓰는 gpt-5.6-terra가 1순위.
DEFAULT_MODELS = [m.strip() for m in os.environ.get(
    "LLM_MODELS",
    "openai/gpt-5.6-terra,anthropic/claude-sonnet-4-6,google/gemini-3.1-flash-lite"
).split(",") if m.strip()]


def complete(system, user, models=None, temperature=0.2, timeout=90, retries=2,
             max_tokens=None):
    """system+user → 응답 텍스트. models 사슬을 순서대로, 각 모델 retries회 시도.
    전부 실패하면 RuntimeError. 키 없으면 즉시 RuntimeError."""
    if not KEY:
        raise RuntimeError("OPENROUTER_API_KEY 없음(env·~/xbot/.env 모두)")
    last = None
    for model in (models or DEFAULT_MODELS):
        model = model.strip()
        if not model:
            continue
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if max_tokens:
            body["max_tokens"] = max_tokens
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(
                    URL, data=json.dumps(body).encode(),
                    headers={"Authorization": f"Bearer {KEY}",
                             "Content-Type": "application/json", "HTTP-Referer": "https://ai-news-daily.local", "X-Title": "aidaily"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    res = json.loads(r.read().decode())
                txt = res["choices"][0]["message"]["content"]
                if txt and txt.strip():
                    print(f"[llm] ok model={model} (try {attempt})", file=sys.stderr)
                    return txt
            except Exception as e:  # noqa
                last = e
                print(f"[llm] {model} try {attempt}/{retries} 실패: {type(e).__name__}",
                      file=sys.stderr)
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"OpenRouter 전 모델 실패: {last}")


def complete_json(system, user, **kw):
    """complete 후 JSON(배열/객체) 추출(코드펜스 제거). 실패 시 None."""
    txt = complete(system, user, **kw)
    txt = re.sub(r"```(json)?", "", txt).replace("```", "").strip()
    m = re.search(r"[\[{].*[\]}]", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


if __name__ == "__main__":
    # 스모크 테스트: python3 -m briefer.llm
    print("key:", "있음" if KEY else "없음", "· models:", DEFAULT_MODELS, file=sys.stderr)
    out = complete("너는 간결한 한국어 비서다.",
                   "다음을 한 문장으로: 오픈라우터 통일 테스트. '통일'과 '작동'을 포함해 답하라.",
                   retries=2)
    print("RESULT:", out.strip())
