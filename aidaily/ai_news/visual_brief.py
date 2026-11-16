"""Original-article enrichment and structured visual briefs for AI News covers."""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from aidaily.integrations import article_reader, openrouter


MODEL = os.environ.get(
    "AI_NEWS_VISUAL_BRIEF_MODEL",
    os.environ.get("AI_NEWS_SUMMARY_MODEL", "openai/gpt-6-luna"),
)
LAYOUTS = {"flow", "comparison", "timeline", "relationship"}

SYSTEM = (
    "너는 뉴스 인포그래픽의 정보설계자다. 기사 원문에서 그림으로 표현할 사실만 추출한다. "
    "원문에 없는 관계·수치·평가를 만들지 않는다. 기사마다 다음 JSON 필드를 작성한다. "
    "message=패널의 한 줄 핵심 메시지(55자 이내), layout=flow/comparison/timeline/relationship 중 하나, "
    "nodes=도식에 놓을 짧은 노드 2~6개(각 24자 이내), metrics=강조할 수치·기한 0~4개, "
    "constraints=기사에 명시된 과제·위험·전제만 0~3개(각 32자 이내). 장점이나 목표를 과제로 바꾸지 말고, 없으면 빈 배열. "
    "긴 설명문, 디자인 지시, 이모지는 쓰지 않는다. 출력은 JSON 배열만 쓴다: "
    '[{"n":"01","message":"...","layout":"flow","nodes":["..."],'
    '"metrics":["..."],"constraints":["..."]}]'
)


def _sentences(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value or "")
            if part.strip()]


def _fallback(story: dict) -> dict:
    facts = [str(value).strip() for value in (story.get("body_bullets") or [])
             if str(value).strip()]
    if not facts:
        facts = _sentences(str(story.get("body") or ""))[:3]
    why = [str(value).strip() for value in (story.get("why_bullets") or [])
           if str(value).strip()]
    if not why:
        why = _sentences(str(story.get("takeaway") or ""))[:2]
    joined = " ".join(facts)
    metrics = re.findall(
        r"(?:20\d{2}년|\d[\d,.]*(?:%|명|억달러|억원|조원|시간|배|건|개))",
        joined,
    )[:4]
    layout = "timeline" if re.search(r"20\d{2}년|단계|부터|까지", joined) else "flow"
    if re.search(r"\bvs\b|대비|반면|보다", joined, re.I):
        layout = "comparison"
    return {
        "n": str(story.get("n") or ""),
        "message": str(story.get("headline") or "")[:55],
        "layout": layout,
        "nodes": [fact[:24].rstrip() for fact in facts[:4]],
        "metrics": list(dict.fromkeys(metrics)),
        "constraints": [item[:32].rstrip() for item in why[:2]],
    }


def _valid(item) -> bool:
    if not isinstance(item, dict):
        return False
    nodes = [str(value).strip() for value in (item.get("nodes") or []) if str(value).strip()]
    return (
        bool(str(item.get("message") or "").strip())
        and str(item.get("layout") or "") in LAYOUTS
        and 2 <= len(nodes) <= 6
    )


def _call(stories: list[dict]):
    items = []
    for story in stories:
        article = str(story.get("article_text") or "").strip()
        if not article:
            article = " ".join(filter(None, [
                str(story.get("body") or ""),
                str(story.get("takeaway") or ""),
            ]))
        items.append({
            "n": str(story.get("n") or ""),
            "headline": str(story.get("headline") or ""),
            "article": article,
        })
    return openrouter.complete_json(
        SYSTEM,
        f"기사 {len(items)}건:\n{json.dumps(items, ensure_ascii=False)}",
        models=[MODEL], temperature=0.1, timeout=120, retries=2, max_tokens=1800,
    )


def _read_originals(stories: list[dict], max_chars: int):
    def read(story):
        url = str(story.get("url") or "")
        try:
            return article_reader.fetch_article_text(url, max_chars=max_chars) if url else ""
        except openrouter.RoutingBlocked:
            raise
        except Exception as exc:  # source failures must not block publication
            print(f"[hero] 원문 수집 실패 {url[:70]}: {type(exc).__name__}", file=sys.stderr)
            return ""

    with ThreadPoolExecutor(max_workers=min(3, len(stories) or 1)) as pool:
        texts = list(pool.map(read, stories))
    for story, text in zip(stories, texts):
        if text:
            story["article_text"] = text
    print(f"[hero] 기사 원문 {sum(bool(text) for text in texts)}/{len(stories)}건 수집",
          file=sys.stderr)


def enrich_stories(stories: list[dict], *, read_originals: bool = True,
                   max_article_chars: int = 6000) -> list[dict]:
    """Attach one validated ``visual_brief`` to every selected story in place."""
    if read_originals:
        _read_originals(stories, max_article_chars)
    parsed = None
    if stories:
        try:
            parsed = _call(stories)
        except openrouter.CompletionPending:
            # Visual-brief extraction is optional enrichment. A busy local LLM
            # must not suppress the actual image generator and its fallback.
            print("[hero] visual brief LLM 대기 → 규칙 기반 폴백", file=sys.stderr)
        except openrouter.RoutingBlocked:
            raise
        except Exception as exc:
            print(f"[hero] visual brief 생성 실패: {type(exc).__name__}", file=sys.stderr)
    by_n = {str(item.get("n") or ""): item for item in (parsed or []) if _valid(item)}
    generated = 0
    for story in stories:
        item = by_n.get(str(story.get("n") or ""))
        if item:
            generated += 1
            story["visual_brief"] = {
                "n": str(story.get("n") or ""),
                "message": str(item["message"]).strip()[:55],
                "layout": str(item["layout"]),
                "nodes": [str(value).strip()[:24] for value in item.get("nodes", [])][:6],
                "metrics": [str(value).strip()[:24] for value in item.get("metrics", [])][:4],
                "constraints": [str(value).strip()[:32]
                                for value in item.get("constraints", [])][:3],
            }
        else:
            story["visual_brief"] = _fallback(story)
    print(f"[hero] visual brief LLM {generated}/{len(stories)}건, 나머지 폴백", file=sys.stderr)
    return stories
