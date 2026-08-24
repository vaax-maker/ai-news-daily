"""HTML rendering — daily mobile page + searchable archive page.

Ported from prototypes:
  - build_proto.py render(): daily-screen CSS + render (hero, infographic cover,
    개조식 story cards, "왜 중요한가", 원문 links, footer). Hardcoded BULLETS
    replaced with outline-generated body_bullets/why_bullets per story.
  - backfill.py render_archive(): archive CSS + JS client-side search.
"""
import datetime
import html
import json
import re

# ---------------------------------------------------------------------------
# Daily page (build_proto.py)
# ---------------------------------------------------------------------------

DAILY_CSS = """
:root{
  --paper:#F7F5F1; --card:#FFFFFF; --ink:#1C1B19; --dim:#55514B; --muted:#928C83;
  --line:rgba(28,27,25,.12); --line-2:rgba(28,27,25,.06);
  --accent:#3450E0; --accent-ink:#25379E; --tint:#EEF0FC; --tint-line:rgba(52,80,224,.22);
  --kr:"Pretendard Variable",Pretendard,-apple-system,system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:#EDEAE4;color:var(--ink);font-family:var(--kr);line-height:1.6;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
.shell{max-width:620px;margin:0 auto;min-height:100vh;position:relative;background:
  radial-gradient(130% 40% at 100% -6%, rgba(52,80,224,.10), transparent 60%), var(--paper);
  box-shadow:0 0 0 1px var(--line-2),0 30px 80px -44px rgba(28,27,25,.42)}
a{color:inherit;text-decoration:none}

/* masthead */
.mast{position:sticky;top:0;z-index:50;display:flex;align-items:center;justify-content:space-between;
  padding:14px 24px;background:rgba(247,245,241,.86);backdrop-filter:blur(14px) saturate(1.1);
  border-bottom:1px solid var(--line)}
.brand{font-weight:800;letter-spacing:.02em;font-size:13px}
.brand b{color:var(--accent-ink);font-weight:800}
.mast .live{font-size:11px;letter-spacing:.05em;color:var(--muted);
  display:flex;align-items:center;gap:6px}
.dot{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:pulse 2.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,80,224,.5)}70%{box-shadow:0 0 0 7px rgba(52,80,224,0)}100%{box-shadow:0 0 0 0 rgba(52,80,224,0)}}

/* hero */
.hero{padding:34px 24px 22px;border-bottom:1px solid var(--line)}
.kick{font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.kick .mk{display:inline-block;width:16px;height:2px;background:var(--accent);vertical-align:middle;margin-right:8px;border-radius:2px}
.hero h1{margin-top:14px;font-size:clamp(26px,7vw,34px);line-height:1.18;font-weight:800;
  letter-spacing:-.022em;text-wrap:balance;color:#191816}
.meta{margin-top:14px;font-size:12px;letter-spacing:.01em;color:var(--muted)}
.summary{margin-top:16px;color:var(--dim);font-size:15.5px;line-height:1.74}
.cover{margin:20px 0 2px;border-radius:16px;overflow:hidden;
  border:1px solid var(--line);background:var(--card);
  box-shadow:0 1px 2px rgba(28,27,25,.05),0 18px 34px -22px rgba(28,27,25,.32)}
.cover img{width:100%;height:auto;display:block}

/* section label */
.seclabel{padding:20px 24px 4px;display:flex;align-items:baseline;gap:12px}
.seclabel .t{font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}
.seclabel .ln{height:1px;flex:1;background:var(--line)}
.seclabel .c{font-size:11px;color:var(--accent);letter-spacing:.06em}

/* stories */
.stories{padding:6px 16px 8px}
.story{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 18px;
  margin:12px 0;box-shadow:0 1px 2px rgba(28,27,25,.04),0 16px 30px -26px rgba(28,27,25,.4)}
.st-row{display:flex;align-items:center;gap:8px;margin-bottom:11px}
.st-no{font-size:12px;font-weight:800;color:var(--accent);letter-spacing:.04em;
  font-variant-numeric:tabular-nums}
.st-head{font-size:19px;line-height:1.34;font-weight:750;letter-spacing:-.012em;
  text-wrap:balance;color:#181715;margin-bottom:12px}

/* 개조식 bullets */
.pts{list-style:none;display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.pts li{position:relative;padding-left:16px;font-size:14.5px;line-height:1.6;color:var(--dim)}
.pts li::before{content:"";position:absolute;left:1px;top:.66em;width:7px;height:2px;
  border-radius:2px;background:var(--accent)}

/* why (핵심) */
.why{margin-top:12px;padding:13px 15px;background:var(--tint);border:1px solid var(--tint-line);
  border-radius:11px}
.why .lbl{display:block;font-size:10px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent-ink);margin-bottom:9px}
.why ul{list-style:none;display:flex;flex-direction:column;gap:7px}
.why li{position:relative;padding-left:15px;font-size:13.5px;line-height:1.56;color:#3f3a34}
.why li::before{content:"\\203A";position:absolute;left:2px;top:-.02em;color:var(--accent);font-weight:700}
.src{margin-top:13px;display:inline-flex;align-items:center;gap:7px;
  font-size:12px;font-weight:700;letter-spacing:.02em;color:var(--accent-ink);
  border-bottom:1px solid var(--tint-line);padding-bottom:2px}
.src .arw{transition:transform .2s}
.src:active .arw,.src:hover .arw{transform:translateX(3px)}

/* footer */
.foot{padding:26px 24px 46px;border-top:1px solid var(--line);margin-top:10px}
.srchbtn{display:flex;align-items:center;justify-content:space-between;width:100%;
  background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 16px;
  font-size:12.5px;letter-spacing:.02em;color:var(--dim);
  box-shadow:0 1px 2px rgba(28,27,25,.04),0 10px 24px -18px rgba(28,27,25,.3)}
.srchbtn b{color:var(--accent-ink);font-weight:700}
.credit{margin-top:20px;font-size:11.5px;letter-spacing:.02em;color:var(--muted);line-height:1.95}
.credit .tag{color:var(--dim);font-weight:700}

@media (prefers-reduced-motion:no-preference){
  .anim{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}
  .hero .anim{animation-delay:.05s}
  .story{opacity:0;transform:translateY(12px);animation:rise .6s cubic-bezier(.2,.7,.2,1) forwards}
  .story:nth-child(1){animation-delay:.10s}.story:nth-child(2){animation-delay:.17s}
  .story:nth-child(3){animation-delay:.24s}.story:nth-child(4){animation-delay:.31s}
  .story:nth-child(5){animation-delay:.38s}
  @keyframes rise{to{opacity:1;transform:none}}
}
"""


def _li(items):
    return "".join(f"<li>{html.escape(x)}</li>" for x in items)


def _document(title, css, body, og=""):
    """Wrap content in a complete, mobile-ready HTML document (viewport + charset).
    og: 선택적 <meta> 태그 문자열(og:image 등) — <head>에 삽입(카톡/OG 프리뷰용)."""
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"{og}"
        f"<style>{css}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_daily(brief, stories, infographic_src):
    """Render the daily mobile HTML page.

    brief: today's Firestore doc (date/title/summary/...).
    stories: list of story dicts with body_bullets/why_bullets from outline.outline_stories().
    infographic_src: <img src> value (relative path or data URI) for the cover image.
    """
    date = brief.get("date", "")
    try:
        dobj = datetime.date.fromisoformat(date)
        wk = ["월", "화", "수", "목", "금", "토", "일"][dobj.weekday()]
        dl = f"{dobj.year} · {dobj.month:02d}.{dobj.day:02d} · {wk}요일"
    except Exception:
        dl = brief.get("newsTime", "")
    title = html.escape(brief.get("title", ""))
    summary = html.escape(brief.get("summary", ""))
    n = len(stories)
    # 캐시버스트(?d=날짜): 파일명이 infographic.png로 고정이라 이게 없으면 브라우저가 어제 이미지를
    # 캐시로 계속 노출한다(og:image엔 이미 ?d=date가 있으나 화면 img엔 없어 발생). 2026-08-21 수정.
    cover = (f'<div class="cover anim"><img src="{html.escape(infographic_src)}?d={html.escape(date)}" '
              'alt="오늘의 AI 뉴스 인포그래픽"/></div>') if infographic_src else ""

    cards = []
    for i, s in enumerate(stories, 1):
        head = html.escape(s.get("headline", ""))
        url = html.escape(s.get("url", ""))
        body_bullets = s.get("body_bullets") or []
        why_bullets = s.get("why_bullets") or []
        body_ul = f'<ul class="pts">{_li(body_bullets)}</ul>' if body_bullets else ""
        why = (f'<div class="why"><span class="lbl">왜 중요한가</span><ul>{_li(why_bullets)}</ul></div>'
               if why_bullets else "")
        src = (f'<a class="src" href="{url}" target="_blank" rel="noopener">'
               f'원문 기사 <span class="arw">→</span></a>' if url else "")
        num = html.escape(str(s.get("n", i)))
        cards.append(f"""
      <article class="story">
        <div class="st-row"><span class="st-no">{num}</span></div>
        <h2 class="st-head">{head}</h2>
        {body_ul}
        {why}
        {src}
      </article>""")
    cards_html = "\n".join(cards)

    body_html = f"""
  <div class="shell">
    <header class="mast">
      <div class="brand">AI <b>데일리</b></div>
      <div class="live"><span class="dot"></span>오늘의 뉴스</div>
    </header>
    <section class="hero">
      <div class="kick"><span class="mk"></span>VAAX · 오늘의 AI 뉴스</div>
      <h1 class="anim">{title}</h1>
      <div class="meta">{dl}</div>
      <p class="summary anim">{summary}</p>
      {cover}
    </section>
    <div class="seclabel"><span class="t">Today's Top Stories</span><span class="ln"></span><span class="c">{n}건</span></div>
    <main class="stories">
      {cards_html}
    </main>
    <footer class="foot">
      <a class="srchbtn" href="archive.html"><span>지난 뉴스 <b>검색</b> · 아카이브</span><span>→</span></a>
      <div class="credit">
        <span class="tag">VAAX · AI 데일리</span><br>
        매 평일 오전 발행 · AI 자동 요약
      </div>
    </footer>
  </div>"""

    # 카톡/OG 프리뷰: 현재 인포그래픽을 절대 URL로 지정 + 날짜 캐시버스터(뉴스 바뀌면 카톡이 새로 스크랩).
    _SITE = "https://vaax-maker.github.io/ai-news-daily"
    _ogimg = f"{_SITE}/infographic.png?d={html.escape(date)}"
    og = (
        '<meta property="og:type" content="article">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{summary}">\n'
        f'<meta property="og:image" content="{_ogimg}">\n'
        f'<meta property="og:url" content="{_SITE}/">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{_ogimg}">\n'
    )
    return _document("오늘의 AI 뉴스 · " + date, DAILY_CSS, body_html, og=og)


# ---------------------------------------------------------------------------
# Archive page (backfill.py)
# ---------------------------------------------------------------------------

ARCHIVE_CSS = """
:root{--paper:#F7F5F1;--card:#FFF;--ink:#1C1B19;--ink-dim:#55514B;--muted:#928C83;
 --line:rgba(28,27,25,.12);--accent:#3450E0;--accent-ink:#25379E;--tint:#EEF0FC;
 --tint-line:rgba(52,80,224,.22);
 --kr:"Pretendard Variable",Pretendard,-apple-system,system-ui,sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#EDEAE4;font-family:var(--kr);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.shell{max-width:640px;margin:0 auto;min-height:100vh;background:var(--paper);
 border-inline:1px solid rgba(28,27,25,.05)}
.mast{position:sticky;top:0;z-index:10;background:rgba(247,245,241,.9);backdrop-filter:blur(12px);
 border-bottom:1px solid var(--line);padding:16px 22px}
.mast .k{font-size:11px;font-weight:700;letter-spacing:.16em;color:var(--accent);text-transform:uppercase}
.mast h1{font-size:23px;font-weight:800;letter-spacing:-.02em;margin-top:3px}
.mast .n{font-size:12px;color:var(--muted);margin-top:2px}
.mast a.back{font-size:11px;font-weight:700;color:var(--accent-ink);display:inline-block;margin-top:8px;border-bottom:1px solid var(--tint-line)}
.search{padding:16px 22px 4px}
.search input{width:100%;font-family:var(--kr);font-size:16px;color:var(--ink);
 background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 16px;outline:none}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(52,80,224,.15)}
.count{font-size:11px;color:var(--muted);padding:10px 24px 2px;letter-spacing:.05em}
.list{padding:6px 16px 60px;display:flex;flex-direction:column;gap:12px}
.item{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.head{display:flex;gap:14px;padding:16px 18px;cursor:pointer;align-items:flex-start}
.date{font-size:12px;color:var(--accent-ink);font-weight:800;white-space:nowrap;
 padding-top:2px;min-width:80px;font-variant-numeric:tabular-nums}
.date .wd{color:var(--muted);font-weight:400}
.htxt{flex:1}
.htxt .t{font-size:16.5px;font-weight:750;letter-spacing:-.01em;line-height:1.35}
.htxt .s{font-size:13px;color:var(--ink-dim);margin-top:6px;line-height:1.55;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{font-size:11px;color:var(--muted);white-space:nowrap;padding-top:3px}
.body{display:none;padding:2px 18px 18px;border-top:1px solid var(--line)}
.item.open .body{display:block}
.item.open .chev{transform:rotate(90deg)}
.chev{color:var(--accent);transition:transform .2s}
.story{padding:14px 0;border-top:1px dashed var(--line)}
.story:first-child{border-top:none}
.story .sh{font-size:14.5px;font-weight:700;line-height:1.4}
.story .sb{font-size:13px;color:var(--ink-dim);margin-top:6px;line-height:1.6}
.story .why{margin-top:8px;background:var(--tint);border:1px solid var(--tint-line);
 border-radius:8px;padding:9px 12px;font-size:12.5px;color:var(--ink);line-height:1.55}
.story .why b{font-size:10px;font-weight:800;letter-spacing:.12em;color:var(--accent-ink);display:block;margin-bottom:4px;text-transform:uppercase}
.story a.src{font-size:11px;font-weight:700;color:var(--accent-ink);margin-top:8px;display:inline-block;border-bottom:1px solid var(--tint-line)}
mark{background:rgba(52,80,224,.22);color:inherit;border-radius:2px}
.empty{text-align:center;color:var(--muted);padding:50px 20px;font-size:14px}
"""

ARCHIVE_JS = """
const DATA = __DATA__;
const WD = ['일','월','화','수','목','금','토'];
function wd(d){try{const t=new Date(d+'T00:00:00');return WD[t.getDay()];}catch(e){return '';}}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function hl(s,q){s=esc(s);if(!q)return s;const r=new RegExp('('+q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+')','ig');return s.replace(r,'<mark>$1</mark>');}
const listEl=document.getElementById('list'), cntEl=document.getElementById('count');
function render(q){
  q=(q||'').trim();
  const ql=q.toLowerCase();
  const rows=DATA.filter(b=>{
    if(!ql)return true;
    const hay=(b.title+' '+b.summary+' '+b.stories.map(s=>s.headline+' '+s.body+' '+s.takeaway).join(' ')).toLowerCase();
    return hay.includes(ql);
  });
  cntEl.textContent=rows.length+' / '+DATA.length+' 건'+(q?' · "'+q+'"':'');
  if(!rows.length){listEl.innerHTML='<div class="empty">검색 결과가 없습니다.</div>';return;}
  listEl.innerHTML=rows.map((b,i)=>{
    const stories=b.stories.map(s=>`<div class="story"><div class="sh">${hl(s.headline,q)}</div>`+
      (s.body?`<div class="sb">${hl(s.body,q)}</div>`:'')+
      (s.takeaway?`<div class="why"><b>왜 중요한가</b>${hl(s.takeaway,q)}</div>`:'')+
      (s.url?`<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener">원문 기사 →</a>`:'')+
      `</div>`).join('');
    return `<div class="item" data-i="${i}">
      <div class="head" onclick="this.parentNode.classList.toggle('open')">
        <div class="date">${b.date.slice(5).replace('-','.')}<div class="wd">${wd(b.date)}요일</div></div>
        <div class="htxt"><div class="t">${hl(b.title,q)}</div><div class="s">${hl(b.summary,q)}</div></div>
        <div class="meta">${b.stories.length}건 <span class="chev">›</span></div>
      </div>
      <div class="body">${stories}</div>
    </div>`;
  }).join('');
}
document.getElementById('q').addEventListener('input',e=>render(e.target.value));
render('');
"""


def render_archive(items):
    data_json = json.dumps(items, ensure_ascii=False)
    js = ARCHIVE_JS.replace("__DATA__", data_json)
    body = (f'<div class="shell">'
            f'<header class="mast"><div class="k">VAAX · AI NEWS</div>'
            f'<h1>아카이브 · 검색</h1><div class="n">지난 뉴스 {len(items)}건</div>'
            f'<a class="back" href="daily.html">← 오늘의 뉴스</a></header>'
            f'<div class="search"><input id="q" type="search" placeholder="키워드 검색 (예: 오픈AI, 규제, 로봇)"></div>'
            f'<div class="count" id="count"></div>'
            f'<div class="list" id="list"></div>'
            f'</div>\n<script>{js}</script>')
    return _document("AI 뉴스 · 아카이브", ARCHIVE_CSS, body)
