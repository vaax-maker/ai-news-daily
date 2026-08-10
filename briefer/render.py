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
  --paper:#F1F2F5; --card:#FFFFFF; --card-2:#FAFAF8;
  --ink:#171A21; --ink-dim:#4B525E; --muted:#8B929E;
  --line:rgba(23,26,33,.11); --line-2:rgba(23,26,33,.055);
  --gold:#4C7E00; --gold-br:#7CC01A;   /* VAAX 진한 연두 (내부 변수명은 레거시) */
  --mono:ui-monospace,"SF Mono",SFMono-Regular,"JetBrains Mono",Menlo,monospace;
  --kr:"Apple SD Gothic Neo",Pretendard,-apple-system,system-ui,"Malgun Gothic",sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:#E7E8EC;color:var(--ink);font-family:var(--kr);line-height:1.6;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
.shell{max-width:520px;margin:0 auto;min-height:100vh;position:relative;
  background:
    radial-gradient(120% 46% at 86% -8%, rgba(206,155,46,.13), transparent 62%),
    var(--paper);
  box-shadow:0 0 0 1px var(--line-2), 0 30px 80px -40px rgba(23,26,33,.4)}
a{color:inherit;text-decoration:none}

/* masthead */
.mast{position:sticky;top:0;z-index:50;display:flex;align-items:center;justify-content:space-between;
  padding:14px 20px;background:rgba(241,242,245,.82);backdrop-filter:blur(14px) saturate(1.1);
  border-bottom:1px solid var(--line)}
.brand{font-family:var(--mono);font-weight:700;letter-spacing:.14em;font-size:12px;text-transform:uppercase}
.brand b{color:var(--gold);font-weight:700}
.mast .live{font-family:var(--mono);font-size:10px;letter-spacing:.14em;color:var(--muted);
  display:flex;align-items:center;gap:6px}
.dot{width:6px;height:6px;border-radius:50%;background:var(--gold-br);animation:pulse 2.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(206,155,46,.5)}70%{box-shadow:0 0 0 7px rgba(206,155,46,0)}100%{box-shadow:0 0 0 0 rgba(206,155,46,0)}}

/* hero */
.hero{padding:30px 20px 22px}
.dateline{font-family:var(--mono);font-size:11px;letter-spacing:.15em;color:var(--gold);
  text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:16px}
.dateline .bar{height:1px;flex:1;background:linear-gradient(90deg,var(--gold-br),transparent)}
.hero h1{font-size:clamp(27px,7.4vw,36px);line-height:1.16;font-weight:800;letter-spacing:-.022em;
  text-wrap:balance;margin-bottom:15px;color:#12141A}
.summary{color:var(--ink-dim);font-size:15px;line-height:1.72}
.cover{margin:22px 0 2px;border-radius:16px;overflow:hidden;
  border:1px solid var(--line);background:var(--card);
  box-shadow:0 1px 2px rgba(23,26,33,.05),0 18px 34px -22px rgba(23,26,33,.28)}
.cover img{width:100%;height:auto;display:block}

/* section label */
.sec{display:flex;align-items:baseline;gap:12px;padding:10px 20px 2px;margin-top:14px}
.sec .k{font-family:var(--mono);font-size:11px;letter-spacing:.19em;color:var(--muted);text-transform:uppercase}
.sec .n{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.08em}
.sec .rule{height:1px;flex:1;background:var(--line)}

/* stories */
.stories{padding:4px 20px 6px}
.story{display:grid;grid-template-columns:50px 1fr;gap:10px;padding:26px 0;border-top:1px solid var(--line)}
.story:first-child{border-top:none}
.rail{position:relative}
.num{font-family:var(--mono);font-size:29px;font-weight:700;color:var(--gold);
  font-variant-numeric:tabular-nums;line-height:1;letter-spacing:-.02em}
.rail::before{content:"";position:absolute;left:10px;top:44px;bottom:-26px;width:1px;
  background:linear-gradient(180deg,var(--line),transparent)}
.story:last-child .rail::before{display:none}
.st-head{font-size:19px;line-height:1.33;font-weight:750;letter-spacing:-.01em;
  text-wrap:balance;margin-bottom:13px;color:#14161C}

/* 개조식 bullets */
.pts{list-style:none;display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.pts li{position:relative;padding-left:16px;font-size:14.5px;line-height:1.58;color:var(--ink-dim)}
.pts li::before{content:"";position:absolute;left:1px;top:.66em;width:7px;height:2px;
  border-radius:2px;background:var(--gold-br)}

/* why (핵심) */
.why{background:#EEF4E2;border:1px solid rgba(76,126,0,.24);
  border-radius:11px;padding:13px 15px}
.why .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.17em;color:var(--gold);
  text-transform:uppercase;display:block;margin-bottom:9px}
.why ul{list-style:none;display:flex;flex-direction:column;gap:7px}
.why li{position:relative;padding-left:15px;font-size:13.5px;line-height:1.56;color:var(--ink)}
.why li::before{content:"\\203A";position:absolute;left:2px;top:-.02em;color:var(--gold);
  font-family:var(--mono);font-weight:700}
.src{margin-top:14px;display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);
  font-size:11px;letter-spacing:.05em;color:var(--gold);border-bottom:1px solid var(--gold);
  padding-bottom:2px}
.src .arw{transition:transform .2s}
.src:active .arw,.src:hover .arw{transform:translateX(3px)}

/* footer */
.foot{padding:28px 20px 46px;border-top:1px solid var(--line);margin-top:12px}
.srchbtn{display:flex;align-items:center;justify-content:space-between;width:100%;
  background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 16px;
  font-family:var(--mono);font-size:12px;letter-spacing:.05em;color:var(--ink-dim);
  box-shadow:0 1px 2px rgba(23,26,33,.04),0 10px 24px -18px rgba(23,26,33,.3)}
.srchbtn b{color:var(--gold);font-weight:700}
.credit{margin-top:20px;font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;
  color:var(--muted);line-height:1.9}
.credit .tag{color:var(--ink-dim)}

@media (prefers-reduced-motion:no-preference){
  .anim{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}
  .hero .anim{animation-delay:.05s}
  .story{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}
  .story:nth-child(1){animation-delay:.10s}.story:nth-child(2){animation-delay:.17s}
  .story:nth-child(3){animation-delay:.24s}.story:nth-child(4){animation-delay:.31s}
  .story:nth-child(5){animation-delay:.38s}
  @keyframes rise{to{opacity:1;transform:none}}
}
"""


def _li(items):
    return "".join(f"<li>{html.escape(x)}</li>" for x in items)


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
    cover = (f'<div class="cover anim"><img src="{html.escape(infographic_src)}" '
              'alt="오늘의 AI 브리핑 인포그래픽"/></div>') if infographic_src else ""

    cards = []
    for s in stories:
        head = html.escape(s.get("headline", ""))
        url = html.escape(s.get("url", ""))
        body_bullets = s.get("body_bullets") or []
        why_bullets = s.get("why_bullets") or []
        body_ul = f'<ul class="pts">{_li(body_bullets)}</ul>' if body_bullets else ""
        why = (f'<div class="why"><span class="lbl">왜 중요한가</span><ul>{_li(why_bullets)}</ul></div>'
               if why_bullets else "")
        src = (f'<a class="src" href="{url}" target="_blank" rel="noopener">'
               f'원문 기사 <span class="arw">→</span></a>' if url else "")
        cards.append(f"""
        <article class="story">
          <div class="rail"><div class="num">{s['n']}</div></div>
          <div class="body">
            <h2 class="st-head">{head}</h2>
            {body_ul}
            {why}
            {src}
          </div>
        </article>""")
    cards_html = "\n".join(cards)

    body_html = f"""
  <div class="shell">
    <header class="mast">
      <div class="brand">AI <b>BRIEF</b></div>
      <div class="live"><span class="dot"></span>오늘의 브리핑</div>
    </header>
    <section class="hero">
      <div class="dateline anim"><span>{dl}</span><span class="bar"></span></div>
      <p class="summary anim">{summary}</p>
      {cover}
    </section>
    <div class="sec"><span class="k">Today's Top Stories</span><span class="rule"></span><span class="n">{n:02d}건</span></div>
    <main class="stories">
      {cards_html}
    </main>
    <footer class="foot">
      <a class="srchbtn" href="archive.html"><span>지난 브리핑 <b>검색</b> · 아카이브</span><span>→</span></a>
      <div class="credit">
        <span class="tag">VAAX · AI BRIEFING</span><br>
        매 평일 오전 발행
      </div>
    </footer>
  </div>"""

    page = "<title>오늘의 AI 브리핑 · " + date + "</title>\n<style>" + DAILY_CSS + "</style>\n" + body_html
    return page


# ---------------------------------------------------------------------------
# Archive page (backfill.py)
# ---------------------------------------------------------------------------

ARCHIVE_CSS = """
:root{--paper:#F1F2F5;--card:#FFF;--ink:#171A21;--ink-dim:#4B525E;--muted:#8B929E;
 --line:rgba(23,26,33,.11);--yeon:#4C7E00;--yeon-br:#7CC01A;--yeon-tint:#EEF4E2;
 --mono:"SF Mono",ui-monospace,Menlo,monospace;
 --kr:"Apple SD Gothic Neo",Pretendard,-apple-system,system-ui,sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#E7E8EC;font-family:var(--kr);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.shell{max-width:640px;margin:0 auto;min-height:100vh;background:var(--paper);
 border-inline:1px solid rgba(23,26,33,.05)}
.mast{position:sticky;top:0;z-index:10;background:rgba(241,242,245,.9);backdrop-filter:blur(12px);
 border-bottom:1px solid var(--line);padding:16px 22px}
.mast .k{font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--yeon);text-transform:uppercase}
.mast h1{font-size:23px;font-weight:800;letter-spacing:-.02em;margin-top:3px}
.mast .n{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:2px}
.mast a.back{font-family:var(--mono);font-size:11px;color:var(--yeon);display:inline-block;margin-top:8px;border-bottom:1px solid var(--yeon)}
.search{padding:16px 22px 4px}
.search input{width:100%;font-family:var(--kr);font-size:16px;color:var(--ink);
 background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 16px;outline:none}
.search input:focus{border-color:var(--yeon-br);box-shadow:0 0 0 3px rgba(124,192,26,.15)}
.count{font-family:var(--mono);font-size:11px;color:var(--muted);padding:10px 24px 2px;letter-spacing:.05em}
.list{padding:6px 16px 60px;display:flex;flex-direction:column;gap:12px}
.item{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.head{display:flex;gap:14px;padding:16px 18px;cursor:pointer;align-items:flex-start}
.date{font-family:var(--mono);font-size:12px;color:var(--yeon);font-weight:700;white-space:nowrap;
 padding-top:2px;min-width:80px}
.date .wd{color:var(--muted);font-weight:400}
.htxt{flex:1}
.htxt .t{font-size:16.5px;font-weight:750;letter-spacing:-.01em;line-height:1.35}
.htxt .s{font-size:13px;color:var(--ink-dim);margin-top:6px;line-height:1.55;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap;padding-top:3px}
.body{display:none;padding:2px 18px 18px;border-top:1px solid var(--line)}
.item.open .body{display:block}
.item.open .chev{transform:rotate(90deg)}
.chev{color:var(--yeon);transition:transform .2s;font-family:var(--mono)}
.story{padding:14px 0;border-top:1px dashed var(--line)}
.story:first-child{border-top:none}
.story .sh{font-size:14.5px;font-weight:700;line-height:1.4}
.story .sb{font-size:13px;color:var(--ink-dim);margin-top:6px;line-height:1.6}
.story .why{margin-top:8px;background:var(--yeon-tint);border:1px solid rgba(76,126,0,.2);
 border-radius:8px;padding:9px 12px;font-size:12.5px;color:var(--ink);line-height:1.55}
.story .why b{font-family:var(--mono);font-size:10px;letter-spacing:.12em;color:var(--yeon);display:block;margin-bottom:4px;text-transform:uppercase}
.story a.src{font-family:var(--mono);font-size:11px;color:var(--yeon);margin-top:8px;display:inline-block;border-bottom:1px solid var(--yeon)}
mark{background:rgba(124,192,26,.32);color:inherit;border-radius:2px}
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
    return (f"<title>AI 브리핑 · 아카이브</title>\n<style>{ARCHIVE_CSS}</style>\n"
            f'<div class="shell">'
            f'<header class="mast"><div class="k">VAAX · AI BRIEFING</div>'
            f'<h1>아카이브 · 검색</h1><div class="n">지난 브리핑 {len(items)}건</div>'
            f'<a class="back" href="index.html">← 오늘의 브리핑</a></header>'
            f'<div class="search"><input id="q" type="search" placeholder="키워드 검색 (예: 오픈AI, 규제, 로봇)"></div>'
            f'<div class="count" id="count"></div>'
            f'<div class="list" id="list"></div>'
            f'</div>\n<script>{js}</script>')
