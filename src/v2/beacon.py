"""오늘, 세상이 — beacon 생성/렌더 코어.

파이프라인: 오늘 뉴스 후보(feed.extract_news) → xbot LLM(대표 선정 + 경종 메시지
+ 카드 미니 함의) → 구조화 dict → v3 디자인 HTML.

- 생성(generate_beacon)은 xbot LLM 필요 = 맥미니 로컬 전용.
- 렌더(render_html)는 순수 파이썬(의존성 없음) = 어디서나.
"""
from __future__ import annotations
import os
import re
import json
import html
import datetime
from typing import Any

from . import feed
from . import hermes

# 주력 = OpenRouter GPT-5.6 Luna (사용자 확정), 폴백 순.
MODELS = ["openai/gpt-5.6-luna", "anthropic/claude-sonnet-4-6", "google/gemini-3.1-flash-lite"]

# 공개 발행 URL(카톡/텔레그램 티저 링크). VAAX 단톡방 발송은 vaax-notifier가 담당.
BEACON_URL = "https://vaax-maker.github.io/ai-news-daily/v2/beacon.html"

SYSTEM = (
    "너는 VAAX의 'AI·XR 경종 에디터'다. 하루 한 건, 세상의 변화를 독자가 "
    "'정신 차리게' 만드는 대표 메시지를 만든다.\n"
    "원칙: (1) 사실에 없는 것은 절대 쓰지 않는다. 수치·인용·주체·대상·기능을 창작하지 "
    "않는다. 원문에 없는 단어·고유명사를 해석에 추가하지 마라(예: 원문에 카메라만 있으면 "
    "'마이크' 같은 미언급 대상 추가 금지). "
    "(2) 함의(메시지)는 한 문장, 감각적이고 강하게. 그러나 낚시·과장·공포조장 금지. "
    "(3) 해석은 '왜 그것이 그런 뜻인지'를 사실과 연결해 설명한다. 단일 사건을 사회 전체의 "
    "규범·결론으로 단정하거나 예언하지 않는다. "
    "(4) 한국어. 완결된 문장. 이모지·해시태그 금지. "
    "(5) VAAX는 XR·가상현실 커뮤니티다. 이미지·영상 생성 AI(생성형 비디오·이미지, "
    "가상휴먼, 영상/이미지 생성 모델 등)는 핵심 관심 주제이니, 후보에 있으면 대표·카드 "
    "선정에서 우선 고려하고 tags에 관련 태그(영상생성·이미지생성 등)를 넣어라. 단, 관련 "
    "뉴스가 없는 날 억지로 만들지 마라(사실·중요도 우선). "
    "(6) 반드시 JSON만 출력한다(설명 문장 금지)."
)


# ---------- 후보 추출 ----------
def load_candidates(docs_root: str) -> list[dict]:
    items = feed.extract_news("ai", docs_root) + feed.extract_news("xr", docs_root)
    out, seen = [], set()
    for it in items:
        title = (getattr(it, "title", "") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        pub = getattr(it, "published", None)
        out.append({
            "title": title,
            "summary": (getattr(it, "summary", "") or "").strip()[:400],
            "source": getattr(it, "domain", "") or "",
            "category": getattr(it, "category", "") or "",
            "date": pub.strftime("%m.%d") if isinstance(pub, datetime.datetime) else "",
            "url": (getattr(it, "url", "") or "").strip(),
        })
    return out


# ---------- LLM 생성 ----------
def _build_user(cands: list[dict], modu_signal: dict | None = None) -> str:
    lines = []
    for i, c in enumerate(cands):
        s = c["summary"][:180].replace("\n", " ")
        lines.append(f'{i}) [{c["category"].upper()}] {c["title"]}  — {s}  (출처 {c["source"]})')
    body = "\n".join(lines)
    modu = ""
    if modu_signal and modu_signal.get("ok") and modu_signal.get("headlines"):
        hl = "\n".join(f"- {h}" for h in modu_signal["headlines"][:6])
        kw = ", ".join(modu_signal.get("keywords", [])[:15])
        modu = (
            "\n\n[참고 신호 · 모두의 AI 오늘 트렌드]\n"
            "다른 매체가 오늘 주목한 헤드라인이다. **앵글·트렌드 힌트로만** 참고하라.\n"
            f"{hl}\n" + (f"키워드: {kw}\n" if kw else "") +
            "지침: 위 트렌드와 겹치는 후보를 우선 고려하되, 사실(fact)은 반드시 위 '후보 뉴스'에서만 "
            "취하고, 다른 매체의 문장을 그대로 베끼지 마라(우리 문장으로 재작성)."
        )
    schema = '''
다음 후보 뉴스들 중에서 작업하라.

작업:
A. 오늘 가장 '경종'이 되는 대표 뉴스 1건을 고른다(변화·충격·실무 파급이 큰 것).
B. 그 대표 뉴스로 경종 메시지를 만든다.
C. 대표를 제외한 나머지 중 중요한 5건을 카드로 고르고, 각 카드에 한 줄 미니 함의를 붙인다.

반드시 아래 JSON 형식으로만 답하라(다른 말 금지):
{
  "representative_index": <정수>,
  "impact_headline": "<함의 한 문장, 40자 이내, 감각적>",
  "fact": "<대표 뉴스의 사실 한 문장, 반드시 위 요약 근거>",
  "interpretation": "<해석 1~2문장, 사실과 연결>",
  "tags": ["<태그>", "..."],
  "confidence": <0~1 실수>,
  "cards": [
    {"index": <정수>, "mini_impact": "<25자 이내 미니 함의>", "tags": ["<태그>"]},
    ... 총 5개 ...
  ]
}'''
    return f"[오늘의 후보 뉴스]\n{body}\n{schema}{modu}"


def _parse_json(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r'^```(?:json)?\s*', '', s)
    s = re.sub(r'\s*```$', '', s).strip()
    m = re.search(r'\{.*\}', s, re.S)
    if m:
        s = m.group(0)
    return json.loads(s)


def _validate(data: dict, n: int) -> None:
    ri = data.get("representative_index")
    if not isinstance(ri, int) or not (0 <= ri < n):
        raise ValueError(f"representative_index out of range: {ri}")
    if not data.get("impact_headline") or not data.get("fact"):
        raise ValueError("missing impact_headline/fact")
    for card in data.get("cards", []):
        ci = card.get("index")
        if not isinstance(ci, int) or not (0 <= ci < n):
            raise ValueError(f"card index out of range: {ci}")


def generate_beacon(cands: list[dict], models: list[str] | None = None,
                    modu_signal: dict | None = None) -> dict:
    """xbot LLM으로 beacon dict 생성(폴백 체인). 맥미니 로컬 전용.

    modu_signal: 모두의 AI 오늘 트렌드(앵글·키워드 힌트, 04 §4.5). None이면 미사용.
    """
    if not hermes.container_up():
        raise RuntimeError("hermes-xbot 컨테이너가 실행 중이 아닙니다 (Docker/xbot 확인).")
    models = models or MODELS
    user = _build_user(cands, modu_signal)
    last = None
    for model in models:
        try:
            data = _parse_json(hermes.complete(SYSTEM, user, model=model))
            _validate(data, len(cands))
            data["_model"] = model
            return data
        except Exception as e:  # noqa
            last = f"{model}: {e}"
            continue
    raise RuntimeError(f"모든 모델 실패: {last}")


# ---------- 렌더 (순수 파이썬) ----------
def _esc(s: Any) -> str:
    return html.escape(str(s or ""))


def _inner(text: Any, url: str) -> str:
    """제목 텍스트를 원문 링크(새 탭)로 감싼다. url 없으면 텍스트만."""
    t = _esc(text)
    if url:
        return f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{t}</a>'
    return t


def _css() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "v2", "beacon.css")
    with open(os.path.abspath(path), encoding="utf-8") as f:
        return f.read()


_SENT_SPLIT = re.compile(r'(?<=[.!?다요”\'])\s+')


def build_message(gen: dict, date: str, url: str = BEACON_URL, limit: int = 400) -> str:
    """카톡/텔레그램 티저(≤400자). 경종 전문(함의·사실·해석)을 문장별 줄바꿈, 월간 링크 제외.
    발송은 vaax-notifier(백엔드)가 담당 — 여기서는 텍스트만 생성한다."""
    head = (gen.get("impact_headline") or "").strip()
    fact = (gen.get("fact") or "").strip()
    interp = (gen.get("interpretation") or "").strip()
    interp_lines = [s.strip() for s in _SENT_SPLIT.split(interp) if s.strip()]
    notice = "※ AI가 자동 취합·요약·사실검증한 콘텐츠입니다. 정확한 내용은 원문을 확인하세요."

    def compose(ilines: list[str]) -> str:
        body = "\n".join([head, "", fact, *ilines]).strip()
        return f"[오늘, 세상이] {date}\n\n{body}\n\n▸ 전문 {url}\n{notice}"

    msg = compose(interp_lines)
    while len(msg) > limit and interp_lines:      # 초과 시 해석 문장을 뒤에서부터 제거
        interp_lines = interp_lines[:-1]
        msg = compose(interp_lines)
    if len(msg) > limit:                          # 그래도 초과면 함의+링크+고지로 축약
        msg = f"[오늘, 세상이] {date}\n\n{head}\n\n▸ 전문 {url}\n{notice}"
    return msg


def render_html(cands: list[dict], gen: dict, date: str) -> str:
    rep = cands[gen["representative_index"]]
    tags_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in gen.get("tags", [])[:4])

    rail = "\n".join(
        f'<div class="live__item{" is-today" if i == gen["representative_index"] else ""}">'
        f'<span class="live__date">{_esc(c["date"])}</span>'
        f'<span class="live__t">{_inner(c["title"], c.get("url"))}</span></div>'
        for i, c in enumerate(cands[:6]))

    cards = []
    for n, card in enumerate(gen.get("cards", []), 1):
        c = cands[card["index"]]
        kw = (card.get("tags") or ["신호"])[0]
        ctags = "".join(f'<span class="tag">{_esc(t)}</span>' for t in card.get("tags", [])[:2])
        cards.append(
            f'<article class="card"><div class="thumb"><span class="thumb__ghost">{n:02d}</span>'
            f'<span class="thumb__kw">{_esc(kw)}</span></div><div class="card__body">'
            f'<div class="card__tags">{ctags}</div>'
            f'<h3 class="card__title">{_inner(c["title"], c.get("url"))}</h3>'
            f'<p class="card__point"><b>{_esc(card.get("mini_impact",""))}</b></p>'
            f'<div class="card__src">{_esc(c["source"]).upper()}</div></div></article>')
    cards_html = "\n".join(cards)

    month = date.split(".")[1].lstrip("0") if "." in date else ""
    model = gen.get("_model", "xbot")
    conf = gen.get("confidence", "")
    return f'''<style>
{_css()}
</style>
<div class="wake"><div class="wrap">
  <header class="mast">
    <div class="mast__brand">오늘, 세상이<span class="sub">VAAX</span></div>
    <div class="mast__meta">{_esc(date)} &nbsp;·&nbsp; <span class="mast__cad">매일 오전 10시 발행</span></div>
  </header>
  <section class="hero">
    <div class="lead">
      <div class="lead__eyebrow">오늘의 경종</div>
      <h1 class="lead__msg">{_esc(gen["impact_headline"])}</h1>
      <div class="lead__fact"><span class="k">대표 뉴스</span><span class="v">{_esc(gen["fact"])}</span></div>
      {f'<p class="lead__interp">{_esc(gen["interpretation"])}</p>' if gen.get("interpretation") else ''}
      <div class="lead__tags">{tags_html}</div>
      {f'<a class="lead__src" href="{_esc(rep.get("url"))}" target="_blank" rel="noopener noreferrer">대표 뉴스 원문 →</a>' if rep.get("url") else ''}
    </div>
    <aside class="live">
      <div class="live__head"><h2>오늘의 신호 · 전체</h2><span class="live__badge">LIVE · {_esc(date[-5:])}</span></div>
      {rail}
      <div class="live__all">전체 {len(cands)}건</div>
    </aside>
  </section>
  <section class="sec">
    <div class="sec__head"><span class="sec__eyebrow">Curated signals</span><h2>오늘의 다른 신호</h2><span class="more">{_esc(date)} · 큐레이션 {len(gen.get("cards",[]))}건</span></div>
    <div class="grid">
{cards_html}
    </div>
  </section>
  <a class="monthly" href="#" onclick="return false">
    <span class="monthly__ghost">{month}</span>
    <div class="monthly__k">이번 달 총집 · 되돌아보기</div>
    <h2 class="monthly__h">이번 달, 세상이 이렇게 바뀌었다.</h2>
    <p class="monthly__sub">한 달치 경종을 하나의 흐름으로 — 변화의 가속을 한눈에.</p>
    <span class="monthly__arrow">월간 총집 열기 <span class="sig">→</span></span>
  </a>
  <footer class="foot">
    <span>VAAX · 오늘, 세상이 <span class="sig">·</span> <a href="archive.html" style="color:var(--signal);text-decoration:none">전체 아카이브·검색</a> <span class="sig">·</span> <a href="../old.html" style="color:var(--muted);text-decoration:none">old</a></span>
    <span>매일 오전 10시 <span class="sig">·</span> 웹 본진 <span class="sig">·</span> 텔레그램 티저</span>
    <span class="sig">xbot LLM 생성({_esc(model)}) · conf {_esc(conf)}</span>
  </footer>
</div></div>'''
