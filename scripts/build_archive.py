#!/usr/bin/env python3
"""오늘, 세상이 — 누적 아카이브(검색) 빌더.

docs/{ai,xr}/daily/*.html 의 **모든 수집 기사**(beacon에 노출된 것 + 안 된 것 전부)를
취합·중복제거 → docs/v2/archive.json (압축) + docs/v2/archive.html (클라이언트 검색).

순수 파싱(LLM 불요) → GitHub Actions(daily-news.yml)에서 자동 갱신 가능.
  python scripts/build_archive.py
"""
import os
import sys
import re
import glob
import json
from bs4 import BeautifulSoup

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from src.v2.beacon import _css  # 디자인 토큰 재사용  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
OUT_JSON = os.path.join(DOCS, "v2", "archive.json")
OUT_HTML = os.path.join(DOCS, "v2", "archive.html")


def gather() -> list[dict]:
    """일별 아카이브 전체에서 기사 취합(url 기준 중복제거, 최신일 우선)."""
    items: dict[str, dict] = {}
    for cat in ("ai", "xr"):
        for p in sorted(glob.glob(os.path.join(DOCS, cat, "daily", "*.html"))):
            date = os.path.basename(p)[:10]  # YYYY-MM-DD
            try:
                with open(p, encoding="utf-8") as f:
                    soup = BeautifulSoup(f, "html.parser")
            except Exception:
                continue
            for art in soup.select("article.news-item"):
                a = art.select_one("h2.news-title a")
                if not a:
                    continue
                title = re.sub(r"\s*NEW\s*$", "", a.get_text(strip=True))
                if not title:
                    continue
                url = (a.get("href") or "").strip()
                key = url or title
                meta = art.select_one(".news-meta .source-link")
                src = meta.get_text(strip=True) if meta else ""
                if key not in items:
                    items[key] = {"t": title, "u": url, "s": src, "d": date, "c": cat}
                elif date > items[key]["d"]:
                    items[key]["d"] = date
    return sorted(items.values(), key=lambda x: x["d"], reverse=True)


_JS = """
const R=document.getElementById('results'),Q=document.getElementById('q'),C=document.getElementById('count');
let DATA=[];
function esc(s){return (s||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}
function render(q){
  q=(q||'').trim().toLowerCase();
  const f=q?DATA.filter(x=>(x.t+' '+x.s).toLowerCase().includes(q)):DATA;
  C.textContent=f.length.toLocaleString()+'건'+(q?' · 검색 결과':' · 전체');
  R.innerHTML=f.slice(0,300).map(x=>`<a class="arow" href="${esc(x.u)}" target="_blank" rel="noopener noreferrer"><span class="ad">${x.d}</span><span class="ac ${x.c}">${x.c.toUpperCase()}</span><span class="at">${esc(x.t)}</span><span class="as">${esc(x.s)}</span></a>`).join('')
    +(f.length>300?'<div class="amore">상위 300건만 표시 — 검색으로 좁혀 보세요</div>':'');
}
fetch('archive.json').then(r=>r.json()).then(d=>{DATA=d;render('');});
Q.addEventListener('input',e=>render(e.target.value));
"""

_EXTRA = """
.awrap{max-width:1080px;margin:0 auto;padding:0 clamp(18px,5vw,52px)}
.asearch{position:sticky;top:0;background:var(--paper);padding:18px 0;border-bottom:1px solid var(--line);z-index:5}
.asearch input{width:100%;box-sizing:border-box;font-family:var(--font-body);font-size:16px;color:var(--ink);
  background:var(--paper-2);border:1px solid var(--line);border-radius:8px;padding:14px 16px;outline:none}
.asearch input:focus{border-color:var(--signal)}
.acount{font-family:var(--font-mono);font-size:12px;color:var(--muted);margin:14px 0 6px;font-variant-numeric:tabular-nums}
.arow{display:grid;grid-template-columns:88px 44px 1fr auto;gap:14px;align-items:baseline;
  padding:13px 6px;border-top:1px solid var(--line);text-decoration:none;color:inherit}
.arow:hover{background:var(--paper-2)}
.ad{font-family:var(--font-mono);font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.ac{font-family:var(--font-mono);font-size:10px;letter-spacing:.08em;color:var(--muted);border:1px solid var(--line);border-radius:2px;padding:2px 6px;text-align:center;height:fit-content}
.ac.ai{color:var(--ink);border-color:#cfcdc5}
.at{font-family:var(--font-display);font-weight:600;font-size:15px;line-height:1.4;letter-spacing:-.01em}
.arow:hover .at{color:var(--signal)}
.as{font-family:var(--font-mono);font-size:11px;color:var(--muted);white-space:nowrap}
.amore{font-family:var(--font-mono);font-size:12px;color:var(--muted);text-align:center;padding:26px 0}
@media(max-width:640px){.arow{grid-template-columns:1fr auto;gap:4px 10px}.ad{grid-row:2}.ac{grid-row:2;justify-self:start}.as{display:none}.at{grid-column:1/3}}
"""


def render(n: int) -> str:
    return f'''<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>오늘, 세상이 · 아카이브 · VAAX</title>
<style>
{_css()}
{_EXTRA}
</style></head><body>
<div class="wake"><div class="wrap awrap">
  <header class="mast">
    <div class="mast__brand"><a href="beacon.html" style="color:inherit;text-decoration:none">오늘, 세상이</a><span class="sub">VAAX · 아카이브</span></div>
    <div class="mast__meta"><a href="beacon.html" style="color:var(--signal);text-decoration:none">← 오늘의 경종</a></div>
  </header>
  <section class="sec" style="padding-top:24px">
    <div class="sec__head"><span class="sec__eyebrow">Archive · Search</span><h2>수집 기사 전체</h2></div>
    <p style="color:var(--muted);font-size:14px;margin:-8px 0 4px">경종에 노출된 기사와 노출되지 않은 기사까지, 수집된 AI·XR 뉴스 전체 누적본입니다.</p>
    <div class="asearch"><input id="q" type="search" placeholder="제목·출처로 검색 (예: 오픈AI, 영상생성, 삼성)" autocomplete="off"></div>
    <div class="acount" id="count">불러오는 중…</div>
    <div id="results"></div>
  </section>
  <footer class="foot"><span>VAAX · 오늘, 세상이 · 아카이브</span><span class="sig">누적 {n:,}건</span></footer>
</div></div>
<script>{_JS}</script>'''


def main():
    items = gather()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(render(len(items)))
    print(f"[archive] {len(items)}건 → v2/archive.json ({os.path.getsize(OUT_JSON)//1024}KB) + archive.html")


if __name__ == "__main__":
    main()
