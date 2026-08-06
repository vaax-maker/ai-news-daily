"""월간 총집 — "이번 달, 세상이 이렇게 바뀌었다" (04 §3.3).

그달의 일간 뉴스(있으면 일간 beacon)를 재료로 LLM이 한 달의 흐름을 하나의 서사로
응축한다. 되돌아볼 자산이자 재방문 축.

부트스트랩: 아직 일간 beacon 축적이 적으므로 그달 뉴스 아카이브(docs/{ai,xr}/daily/
{month}-*.html)에서 헤드라인을 모아 합성한다. 사실은 제공 헤드라인에서만(과장·창작 금지).
"""
from __future__ import annotations
import os
import re
import glob
import json
from bs4 import BeautifulSoup

from . import hermes
from .beacon import _css, _esc

MODELS = ["openai/gpt-5.6-luna", "anthropic/claude-sonnet-4-6", "google/gemini-3.1-flash-lite"]


def gather_month(month: str, docs_root: str, per_day: int = 2) -> list[dict]:
    """month='YYYY-MM'. 그달 일간 파일에서 상위 per_day 헤드라인씩 수집."""
    items = []
    for cat in ("ai", "xr"):
        for path in sorted(glob.glob(os.path.join(docs_root, cat, "daily", f"{month}-*.html")), reverse=True):
            date = os.path.basename(path)[:10]
            with open(path, encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
            n = 0
            for art in soup.select("article.news-item"):
                a = art.select_one("h2.news-title a")
                if not a:
                    continue
                title = re.sub(r"\s*NEW\s*$", "", a.get_text(strip=True))
                body = art.select_one(".news-summary, .news-body")
                summary = body.get_text(" ", strip=True)[:160] if body else ""
                items.append({"date": date, "category": cat, "title": title, "summary": summary})
                n += 1
                if n >= per_day:
                    break
    seen, out = set(), []
    for it in items:
        if it["title"] and it["title"] not in seen:
            seen.add(it["title"])
            out.append(it)
    # 노출순서: 가까운 날짜가 위로(최신순) — 합성 재료를 최신→과거로 정렬
    return sorted(out, key=lambda x: x["date"], reverse=True)


_SYS = (
    "너는 VAAX 월간 에디터다. 한 달간의 AI·XR 변화를 독자가 큰 흐름으로 체감하도록 "
    "하나의 서사로 응축한다. 사실은 제공된 헤드라인에서만 취하고, 과장·창작하지 않는다. "
    "한국어. 반드시 JSON만 출력한다."
)


def generate_monthly(items: list[dict], month: str, models: list[str] | None = None) -> dict:
    if not hermes.container_up():
        raise RuntimeError("hermes-xbot 컨테이너 미실행")
    lines = "\n".join(
        f'{it["date"][5:]} [{it["category"].upper()}] {it["title"]} — {it["summary"]}'
        for it in items)
    user = (
        f"[{month} 헤드라인]\n{lines}\n\n"
        "작업: 이 달의 변화를 응축하라. 반드시 JSON만:\n"
        '{"headline":"<이 달을 한 문장으로, 40자 이내, 감각적>",'
        '"points":["<이 달의 큰 흐름을 개조식으로 한 줄씩, 명사형 종결>", ... 3~4개],'
        '"shifts":[{"impact":"<핵심 변화 함의 한 줄>","why":"<근거 한 줄>"}, ... 5~7개],'
        '"next_watch":["<다음 달 관전 포인트>", ...3개]}'
    )
    last = None
    for model in (models or MODELS):
        try:
            raw = hermes.complete(_SYS, user, model=model, timeout=180)
            s = re.sub(r'^```(?:json)?\s*', '', raw.strip())
            s = re.sub(r'\s*```$', '', s).strip()
            m = re.search(r'\{.*\}', s, re.S)
            data = json.loads(m.group(0) if m else s)
            data["_model"] = model
            return data
        except Exception as e:  # noqa
            last = f"{model}: {e}"
    raise RuntimeError(f"월간 생성 실패: {last}")


_EXTRA_CSS = """
.mhero{background:var(--hero);color:var(--hero-ink);border-radius:10px;padding:clamp(30px,5vw,56px)}
.mhero__k{font-family:var(--font-mono);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--signal);margin-bottom:18px}
.mhero__h{font-family:var(--font-display);font-weight:800;font-size:clamp(28px,5vw,50px);line-height:1.1;letter-spacing:-.02em;text-wrap:balance;margin:0}
.mhero__n{color:var(--hero-muted);font-size:16px;line-height:1.75;margin:22px 0 0;max-width:70ch}
.mhero__pts{list-style:none;margin:22px 0 0;padding:0;max-width:74ch}
.mhero__pts li{position:relative;padding-left:20px;margin:11px 0;color:var(--hero-ink);font-size:16px;line-height:1.6}
.mhero__pts li::before{content:"";position:absolute;left:0;top:11px;width:6px;height:6px;border-radius:50%;background:var(--signal)}
.mshifts{list-style:none;padding:clamp(30px,5vw,52px) 0 0;margin:0}
.mshift{display:grid;grid-template-columns:44px 1fr;gap:18px;padding:20px 0;border-top:1px solid var(--line)}
.mshift:first-child{border-top:0}
.mshift__i{font-family:var(--font-mono);font-size:13px;color:var(--signal);font-variant-numeric:tabular-nums;padding-top:4px}
.mshift__t{font-family:var(--font-display);font-weight:700;font-size:clamp(17px,2.4vw,21px);line-height:1.3;letter-spacing:-.01em}
.mshift__w{color:var(--muted);font-size:14px;line-height:1.65;margin-top:6px}
.mwatch{margin:clamp(30px,5vw,48px) 0 0;border-top:1px solid var(--line);padding-top:26px}
.mwatch__k{font-family:var(--font-mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--signal);margin-bottom:16px}
.mwatch__row{display:flex;flex-wrap:wrap;gap:10px}
.mwatch__x{border:1px solid var(--line);border-radius:2px;padding:9px 14px;font-size:14px;color:var(--ink)}
"""


def render_monthly(data: dict, month: str, count: int) -> str:
    y, m = month.split("-")
    mlabel = f"{y}년 {int(m)}월"
    shifts = "".join(
        f'<li class="mshift"><span class="mshift__i">{i:02d}</span>'
        f'<div><div class="mshift__t">{_esc(s.get("impact",""))}</div>'
        f'<div class="mshift__w">{_esc(s.get("why",""))}</div></div></li>'
        for i, s in enumerate(data.get("shifts", []), 1))
    watch = "".join(f'<span class="mwatch__x">{_esc(w)}</span>' for w in data.get("next_watch", []))
    model = data.get("_model", "xbot")
    return f'''<style>
{_css()}
{_EXTRA_CSS}
</style>
<div class="wake"><div class="wrap">
  <header class="mast">
    <div class="mast__brand">오늘, 세상이<span class="sub">VAAX · 월간</span></div>
    <div class="mast__meta">{_esc(mlabel)} 총집 &nbsp;·&nbsp; <span class="mast__cad">월간 발행</span></div>
  </header>
  <section class="mhero">
    <div class="mhero__k">이번 달, 세상이 이렇게 바뀌었다</div>
    <h1 class="mhero__h">{_esc(data.get("headline",""))}</h1>
    <ul class="mhero__pts">{"".join(f"<li>{_esc(p)}</li>" for p in (data.get("points") or ([data["narrative"]] if data.get("narrative") else [])))}</ul>
  </section>
  <section class="sec">
    <div class="sec__head"><span class="sec__eyebrow">Key shifts</span><h2>이 달의 결정적 변화</h2><span class="more">{_esc(mlabel)} · {count}건 헤드라인 응축</span></div>
    <ul class="mshifts">{shifts}</ul>
    <div class="mwatch"><div class="mwatch__k">다음 달 관전 포인트</div><div class="mwatch__row">{watch}</div></div>
  </section>
  <footer class="foot">
    <span>VAAX · 오늘, 세상이 · 월간 총집</span>
    <span>매일=경종 <span class="sig">·</span> 매월=응축</span>
    <span class="sig">xbot LLM 생성({_esc(model)})</span>
  </footer>
</div></div>'''
