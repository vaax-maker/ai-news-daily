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
    "너는 엄격한 뉴스 사실검증관이다. 주어진 '사실(fact)'이 '원문 요약'으로 뒷받침되는지, "
    "그리고 '함의/해석'이 사실을 넘어 과장·예언·창작을 하지 않았는지 평가한다. "
    "확신이 없으면 보수적으로 판정한다. 반드시 JSON만 출력한다."
)


def judge(gen: dict, cands: list[dict], model: str = "openai/gpt-5.6-luna") -> dict:
    rep = cands[gen["representative_index"]]
    user = (
        f'원문 요약: {rep.get("summary","")}\n---\n'
        f'함의: {gen.get("impact_headline","")}\n'
        f'사실: {gen.get("fact","")}\n'
        f'해석: {gen.get("interpretation","")}\n---\n'
        '아래 JSON만 출력:\n'
        '{"ok": true 또는 false, "fact_grounded": 0~1 실수, '
        '"no_overclaim": 0~1 실수, "issues": ["문제 요약", ...]}\n'
        'fact가 원문에 근거하고 해석이 과장·창작이 아니면 ok=true.'
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
    passed = (not ev) and (jd.get("ok") is not False)
    return {"passed": passed, "evidence_issues": ev, "judge": jd}
