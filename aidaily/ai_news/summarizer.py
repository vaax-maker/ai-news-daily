#!/usr/bin/env python3
"""개조식 자동 변환 — 소스 스토리(주요내용/핵심포인트 문장) → 핵심 bullet.
공통 LLM 클라이언트로 호출. 사실 충실·창작 금지. 실패 시 문장분할 폴백."""
import json
import os
import re
import sys

from aidaily.integrations import openrouter

MODEL = os.environ.get(
    "AI_NEWS_SUMMARY_MODEL",
    os.environ.get("OUTLINE_MODEL", "openai/gpt-6-luna"),
)

SYS = (
 "너는 한국어 뉴스 요약 편집자다. 각 뉴스의 '주요내용'과 '핵심포인트' 문장을 "
 "개조식 bullet로 압축한다. 규칙: (1) 원문 사실만, 수치·고유명사·인용 그대로, 창작·과장 금지. "
 "(2) body는 원문에 서로 다른 사실이 충분하면 반드시 3개, why(왜 중요한가)는 1~2개. "
 "(3) body 각 bullet은 45~55자 내외(허용 35~65자)의 완결된 개조식 문장으로 쓴다. "
 "문장을 중간에서 자르거나 제목만 바꿔 쓰지 말고, 세 불릿을 합쳐 기사 핵심이 충분히 이해되게 한다. "
 "why도 35~60자로 구체적으로 쓴다. "
 "(4) 이모지 금지. 출력은 JSON 배열만(설명·코드펜스 금지): "
 '[{"n":"01","body":["...","..."],"why":["...","..."]}, ...]'
)


def _call(stories):
    items = [{"n": s["n"], "headline": s["headline"], "body": s["body"],
              "takeaway": s["takeaway"]} for s in stories]
    user = f"입력 뉴스 {len(items)}건:\n{json.dumps(items, ensure_ascii=False)}"
    return openrouter.complete_json(
        SYS, user, models=[MODEL], temperature=0.2, timeout=90, retries=2
    )


def _fallback(stories):
    def split(t, k):
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", t or "") if x.strip()]
        chunks = []
        for sentence in sentences:
            if len(sentence) <= 70:
                chunks.append(sentence)
                continue
            # Prefer complete clauses over arbitrary character truncation.
            clauses = [x.strip() for x in re.split(r"(?<=[,;:])\s*", sentence) if x.strip()]
            current = ""
            for clause in clauses:
                candidate = f"{current} {clause}".strip()
                if current and len(candidate) > 70:
                    chunks.append(current)
                    current = clause
                else:
                    current = candidate
            if current:
                chunks.append(current)
        return chunks[:k]
    return [{"n": s["n"], "body": split(s["body"], 3), "why": split(s["takeaway"], 2)}
            for s in stories]


def _valid_generated(item, story):
    body = [str(value).strip() for value in (item.get("body") or []) if str(value).strip()]
    why = [str(value).strip() for value in (item.get("why") or []) if str(value).strip()]
    source_is_substantial = len(str(story.get("body") or "")) >= 100
    if source_is_substantial and len(body) != 3:
        return False
    if not body or any(len(value) > 75 for value in body):
        return False
    if any(len(value) > 70 for value in why):
        return False
    return True


def summarize_stories(stories):
    parsed = None
    if stories:
        try:
            parsed = _call(stories)
            if parsed and len(parsed) == len(stories):
                print(f"[ai_news] summary ok (usage={openrouter.last_usage()})", file=sys.stderr)
            else:
                parsed = None
        except openrouter.RoutingBlocked:
            raise
        except Exception as e:
            print(f"[ai_news] summary failed: {type(e).__name__}: {str(e)[:140]}", file=sys.stderr)
    if not parsed:
        print("[ai_news] summary fallback (sentence split)", file=sys.stderr)
        parsed = _fallback(stories)
    by_n = {str(x.get("n")): x for x in parsed if isinstance(x, dict)}
    for s in stories:
        x = by_n.get(str(s["n"]), {})
        if not _valid_generated(x, s):
            x = _fallback([s])[0]
        s["body_bullets"] = [str(b).strip() for b in (x.get("body") or []) if str(b).strip()][:3]
        s["why_bullets"] = [str(w).strip() for w in (x.get("why") or []) if str(w).strip()][:2]
    return stories


if __name__ == "__main__":
    SP = sys.argv[1]
    data = json.load(open(f"{SP}/today_stories.json"))
    st = summarize_stories(data["stories"])
    for s in st:
        print(f"\n### {s['n']} {s['headline'][:44]}")
        for b in s["body_bullets"]:
            print("  ·", b)
        print("  [왜 중요한가]")
        for w in s["why_bullets"]:
            print("   -", w)
