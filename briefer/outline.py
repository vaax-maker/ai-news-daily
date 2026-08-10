#!/usr/bin/env python3
"""개조식 자동 변환 — 소스 스토리(주요내용/핵심포인트 문장) → 핵심 bullet.
OpenRouter HTTP(chat completions) 직접 호출. 사실 충실·창작 금지. 실패 시 문장분할 폴백.
키: 환경변수 OPENROUTER_API_KEY."""
import os, json, re, sys, urllib.request

MODEL = os.environ.get("OUTLINE_MODEL", "openai/gpt-5.6-terra")
URL = "https://openrouter.ai/api/v1/chat/completions"
KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

SYS = (
 "너는 한국어 뉴스 요약 편집자다. 각 뉴스의 '주요내용'과 '핵심포인트' 문장을 "
 "개조식 bullet로 압축한다. 규칙: (1) 원문 사실만, 수치·고유명사·인용 그대로, 창작·과장 금지. "
 "(2) body는 핵심 3개 이내, why(왜 중요한가)는 2개 이내. (3) 각 bullet 45자 내외, 명사·간결체. "
 "(4) 이모지 금지. 출력은 JSON 배열만(설명·코드펜스 금지): "
 '[{"n":"01","body":["...","..."],"why":["...","..."]}, ...]'
)


def _call(stories):
    items = [{"n": s["n"], "headline": s["headline"], "body": s["body"],
              "takeaway": s["takeaway"]} for s in stories]
    user = f"입력 뉴스 {len(items)}건:\n{json.dumps(items, ensure_ascii=False)}"
    body = {"model": MODEL, "temperature": 0.2,
            "messages": [{"role": "system", "content": SYS},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.loads(r.read().decode())
    return res["choices"][0]["message"]["content"]


def _extract_json(text):
    text = re.sub(r"```(json)?", "", text).replace("```", "").strip()
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else None


def _fallback(stories):
    def split(t, k):
        return [x.strip() for x in re.split(r"(?<=[다요\.])\s+", t or "") if x.strip()][:k]
    return [{"n": s["n"], "body": split(s["body"], 3), "why": split(s["takeaway"], 2)}
            for s in stories]


def outline_stories(stories):
    parsed = None
    if KEY:
        try:
            parsed = _extract_json(_call(stories))
            if parsed and len(parsed) == len(stories):
                print(f"[outline] OpenRouter ok (model={MODEL})", file=sys.stderr)
            else:
                parsed = None
        except Exception as e:
            print(f"[outline] 실패: {type(e).__name__}: {str(e)[:140]}", file=sys.stderr)
    if not parsed:
        print("[outline] 폴백(문장분할)", file=sys.stderr)
        parsed = _fallback(stories)
    by_n = {str(x.get("n")): x for x in parsed}
    for s in stories:
        x = by_n.get(str(s["n"]), {})
        s["body_bullets"] = [b for b in (x.get("body") or []) if b][:3] or _fallback([s])[0]["body"]
        s["why_bullets"] = [w for w in (x.get("why") or []) if w][:2]
    return stories


if __name__ == "__main__":
    SP = sys.argv[1]
    data = json.load(open(f"{SP}/today_stories.json"))
    st = outline_stories(data["stories"])
    for s in st:
        print(f"\n### {s['n']} {s['headline'][:44]}")
        for b in s["body_bullets"]:
            print("  ·", b)
        print("  [왜 중요한가]")
        for w in s["why_bullets"]:
            print("   -", w)
