"""beacon 검증 게이트 — "그럴듯한 헛소리" 방지 (05 설계 §6·§7).

두 층:
1) evidence_issues(): 결정적(비-LLM) 원문 대조 — fact/headline의 수치가 대표 뉴스
   원문(요약+제목)에 실재하는지. 미확인 수치는 할루시네이션 의심.
2) judge(): LLM 심사관(생성과 별개 프롬프트) — 사실 근거성·과장/창작 여부 평가.

build_beacon 이 생성 후 이 게이트를 돌려, 통과 실패 시 1회 재생성 → 여전히 실패면
degraded 플래그로 표시(로그). 사람 라벨 골든셋(05 §8-1)은 추후.
"""
from __future__ import annotations
import re
import json
from . import hermes

_NUM = re.compile(r'\d[\d,\.]*\d|\d')


def _norm(s: str) -> str:
    return (s or "").replace(",", "").replace(".", "")


def _numbers(s: str) -> list[str]:
    return _NUM.findall(s or "")


def evidence_issues(gen: dict, cands: list[dict]) -> list[str]:
    """결정적 원문 대조. 반환 = 문제 목록(비면 통과)."""
    issues = []
    rep = cands[gen["representative_index"]]
    src = f'{rep.get("summary","")} {rep.get("title","")}'
    src_n = _norm(src)
    if not gen.get("fact"):
        issues.append("fact 비어있음")
    for field in ("fact", "impact_headline"):
        for n in _numbers(gen.get(field, "")):
            if len(_norm(n)) >= 2 and _norm(n) not in src_n:  # 한 자리 수(3건 등)는 관대
                issues.append(f"{field} 수치 '{n}' 원문 미확인")
    return issues


_JUDGE_SYS = (
    "너는 뉴스 사실검증관이다. 아래 기준으로만 판정한다.\n"
    "- 'fact(사실)'는 원문 요약으로 뒷받침되어야 한다. 원문과 모순되거나 원문에 없는 "
    "구체 정보(고유명사·수치·인용·사건)를 지어내면 실패.\n"
    "- '함의(headline)'와 '해석'은 편집적 관점이다. 사실에서 합리적으로 도출되는 "
    "해석·강조·문제제기·전망은 강하거나 도발적이어도 허용한다(그 자체를 과장으로 보지 마라).\n"
    "- 실패(ok=false)는 오직 다음일 때만: (a) fact가 원문을 벗어남, (b) 함의/해석이 원문에 "
    "없는 '구체적 사실(대상·수치·인용·사건)'을 지어냄(fabrication), (c) 원문이 전혀 지지하지 "
    "못하는 단정.\n"
    "- 일반화·규범적 문제제기·감각적 표현·해석적 프레이밍은 실패 사유가 아니다.\n"
    "반드시 JSON만 출력한다."
)


def judge(gen: dict, cands: list[dict], model: str = "openai/gpt-5.6-luna") -> dict:
    rep = cands[gen["representative_index"]]
    user = (
        f'원문 요약: {rep.get("summary","")}\n---\n'
        f'함의: {gen.get("impact_headline","")}\n'
        f'사실: {gen.get("fact","")}\n'
        f'해석: {gen.get("interpretation","")}\n---\n'
        '아래 JSON만 출력:\n'
        '{"ok": true 또는 false, "fact_ok": 0~1 실수, '
        '"fabrication": true 또는 false, "issues": ["문제 요약", ...]}\n'
        'fabrication = 원문에 없는 구체적 사실(대상·수치·인용·사건)을 지어냈는가. '
        'ok = fact가 원문에 근거하고 fabrication이 없으면 true. '
        '함의·해석이 강하거나 해석적이라는 이유만으로는 ok=false로 하지 마라.'
    )
    try:
        raw = hermes.complete(_JUDGE_SYS, user, model=model, timeout=120)
        s = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        s = re.sub(r'\s*```$', '', s).strip()
        m = re.search(r'\{.*\}', s, re.S)
        return json.loads(m.group(0) if m else s)
    except Exception as e:  # noqa
        return {"ok": None, "issues": [f"judge 실패: {e}"]}


def evaluate(gen: dict, cands: list[dict], model: str | None = None) -> dict:
    """게이트 종합. passed = 결정적 이슈 없음 AND judge ok != False."""
    ev = evidence_issues(gen, cands)
    jd = judge(gen, cands, model=model or "openai/gpt-5.6-luna")
    passed = (not ev) and (jd.get("ok") is not False) and (jd.get("fabrication") is not True)
    return {"passed": passed, "evidence_issues": ev, "judge": jd}
