#!/usr/bin/env python3
"""
YouTube Summaries renderer — 마크다운을 1페이지 HTML 비주얼 리포트로 변환.

설계 변경 (2026-05-29):
- 슬라이드 페이지넘김 폐기 → 세로 스크롤 단일 페이지 (정보 전달 / 읽기 용도)
- 표지 슬라이드 제거 → 페이지 상단 헤더에 브랜드·날짜·제목·요약 배치
- 12-grid 카드 레이아웃 → 섹션 무게에 따라 span 4/6/12 자동 배치 (빈공간 최소)
- 인포그래픽 컴포넌트: 스텝 플로우, 통계 카드, 비교 막대 자동 감지 변환

AI Daily의 YouTube Summaries 테마를 적용한다.
- 데이라이트 뉴트럴 + 카테고리 식별색(--category tech|econ|hub → body.cat-*). 헤더색 = 그 글의 주제.
- 목차(TOC) 제거.
- 영상 재생 임베드(--video-url): 16:9 유튜브 플레이어(파싱 실패 시 재생 링크 버튼).

기존 CLI 인자 호환:
  python3 -m aidaily.youtube_summaries.renderer --in note.md --out report.html \
      --eyebrow "YOUTUBE SUMMARIES · 2026-07-02 · 채널명" --badge "🎬 영상" \
      --brand "채널명" --footer "채널명 · 2026-07-02" \
      --video-url "https://youtu.be/..." --category tech
"""
import argparse, re, sys, html as _html

# ── 인라인 처리 ────────────────────────────────────────────────────
def esc(s):
    return _html.escape(s, quote=True)

def _clean_head(h):
    """섹션 제목·소제목 정리 — 마크다운 링크/URL을 제목에 노출하지 않는다.
    예: '챗봇 전환 ([0:46 딥링크](https://...))' → '챗봇 전환'
    (2026-06-08: 출판 페이지 소제목에 링크주소 노출 금지)"""
    h = re.sub(r'\[[^\]]*\]\([^)]*\)', '', h)          # 마크다운 링크 통째 제거
    h = re.sub(r'https?://\S+', '', h)                  # 잔여 bare URL 제거
    h = re.sub(r'\(\s*[·,;/&+\s]*\s*\)', '', h)        # 빈/구분자만 남은 괄호 제거
    h = re.sub(r'\s{2,}', ' ', h).strip(' -·—–')
    return h.strip()

def _inline(s):
    s = esc(s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    # 등락 색상
    s = re.sub(r'(?<![\w$])(\+\d[\d.,]*%?)', r'<span class="up">\1</span>', s)
    s = re.sub(r'(?<![\w$])(-\d[\d.,]*%?)', r'<span class="dn">\1</span>', s)
    s = re.sub(r'(↑|상승|호조|개선)', r'<span class="up">\1</span>', s)
    s = re.sub(r'(↓|하락|악화|감소|위기)', r'<span class="dn">\1</span>', s)
    return s

# ── 영상 재생 (유튜브 임베드) ──────────────────────────────────────
def _yt_id(url):
    """유튜브 URL에서 11자 video id 추출 (watch?v= / youtu.be / shorts / embed)."""
    if not url:
        return ""
    m = re.search(r'(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else ""

def _video_block(url):
    """상단 영상 재생 블록. 유튜브면 16:9 iframe, 아니면 재생 링크 버튼."""
    if not url:
        return ""
    vid = _yt_id(url)
    if vid:
        return (f'<div class="video-wrap"><iframe src="https://www.youtube.com/embed/{vid}" '
                f'title="영상 재생" loading="lazy" allowfullscreen '
                f'allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture">'
                f'</iframe></div>')
    return (f'<div class="video-cta"><a class="play-btn" href="{esc(url)}" '
            f'target="_blank" rel="noopener">▶ 영상 재생</a></div>')

# ── 표 렌더링 ─────────────────────────────────────────────────────
def _render_table(lines):
    rows = []
    for ln in lines:
        if re.match(r'^\|?[\s:|-]+\|?$', ln) and set(ln) <= set('|-: '):
            continue
        rows.append([c.strip() for c in ln.strip().strip('|').split('|')])
    if not rows:
        return "", 0
    rowcount = len(rows) - 1
    out = ['<div class="tbl-wrap"><table><thead><tr>']
    out += [f'<th>{esc(c)}</th>' for c in rows[0]]
    out.append('</tr></thead><tbody>')
    for r in rows[1:]:
        out.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in r) + '</tr>')
    out.append('</tbody></table></div>')
    return ''.join(out), rowcount

# ── 인포그래픽: 번호 매겨진 step flow 감지 ─────────────────────────
_STEP_RE = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*[—\-]\s*(.+)$')

def _detect_steps(lines):
    """'N. **제목** — 설명' 패턴이 2개 이상 연속이면 step 시각화."""
    steps = []
    for ln in lines:
        m = _STEP_RE.match(ln.strip())
        if m:
            steps.append((m.group(1), m.group(2), m.group(3)))
        else:
            return None
    return steps if len(steps) >= 2 else None

def _render_steps(steps):
    items = "".join(
        f'<div class="step"><span class="snum">{esc(n)}</span>'
        f'<div class="sbody"><b>{_inline(t)}</b><span>{_inline(d)}</span></div></div>'
        for n, t, d in steps
    )
    return f'<div class="steps">{items}</div>'

# ── 인포그래픽 펜스 블록(```bars/```kpi/```donut/```timeline) ──────
# 하위호환: 기존 원고엔 코드펜스가 없으므로 동작 변화 0. 색상은 CSS 변수(--accent)만 사용.
_IG_KINDS = ('bars', 'kpi', 'donut', 'timeline')

def _ig_num(v):
    m = re.search(r'-?\d[\d,.]*', v or '')
    return float(m.group(0).replace(',', '')) if m else 0.0

def _ig_rows(lines):
    rows = []
    for ln in lines:
        s = ln.strip().lstrip('-*').strip()
        if s:
            rows.append([c.strip() for c in s.split('|')])
    return rows

def render_infographic(kind, lines):
    """인포그래픽 펜스 → HTML. 알 수 없는 종류/빈 내용은 평문 보존(회귀 안전)."""
    kind = (kind or '').strip().lower()
    rows = _ig_rows(lines)
    if not rows or kind not in _IG_KINDS:
        body = '<br>'.join(_inline(' | '.join(r)) for r in rows)
        return f'<div class="ig-raw">{body}</div>' if body else ''
    if kind == 'bars':
        vals = [_ig_num(r[1]) if len(r) > 1 else 0.0 for r in rows]
        mx = max(vals) or 1.0
        items = ''
        for r, v in zip(rows, vals):
            disp = esc(r[1]) if len(r) > 1 else ''
            note = _inline(r[2]) if len(r) > 2 else ''
            pct = max(2.0, v / mx * 100.0)
            items += (f'<div class="ig-bar"><span class="igb-l">{_inline(r[0])}</span>'
                      f'<span class="igb-track"><span class="igb-fill" style="width:{pct:.1f}%"></span></span>'
                      f'<span class="igb-v">{disp} {note}</span></div>')
        return f'<div class="ig-bars">{items}</div>'
    if kind == 'kpi':
        items = ''
        for r in rows:
            label = _inline(r[1]) if len(r) > 1 else ''
            items += (f'<div class="ig-kpi"><span class="igk-v">{esc(r[0])}</span>'
                      f'<span class="igk-l">{label}</span></div>')
        return f'<div class="ig-kpis">{items}</div>'
    if kind == 'donut':
        items = ''
        for r in rows:
            p = max(0.0, min(100.0, _ig_num(r[1]) if len(r) > 1 else 0.0))
            items += (f'<div class="ig-donut"><span class="igd-ring" '
                      f'style="background:conic-gradient(var(--accent) {p:.0f}%,var(--surface) 0)">'
                      f'<span class="igd-num">{p:.0f}%</span></span>'
                      f'<span class="igd-l">{_inline(r[0])}</span></div>')
        return f'<div class="ig-donuts">{items}</div>'
    items = ''  # timeline
    for r in rows:
        txt = _inline(r[1]) if len(r) > 1 else ''
        items += (f'<div class="ig-tl"><span class="igt-dot"></span>'
                  f'<span class="igt-t">{_inline(r[0])}</span><span class="igt-x">{txt}</span></div>')
    return f'<div class="ig-timeline">{items}</div>'

# ── 마크다운 본문 → HTML (구조 보존) ─────────────────────────────
def md_body(md):
    lines = md.splitlines()
    out, i = [], 0
    body_weight = 0  # 시각 무게 추정용

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.strip().startswith('```'):
            kind = ln.strip()[3:]
            blk = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                blk.append(lines[i]); i += 1
            i += 1  # 닫는 ``` 소비
            out.append(render_infographic(kind, blk))
            body_weight += len(blk) * 0.9 + 1
            continue
        if re.match(r'^-{3,}$', ln.strip()):
            i += 1; continue
        if ln.startswith('### '):
            out.append(f'<h3>{esc(ln[4:].strip())}</h3>')
            body_weight += 1; i += 1; continue
        if ln.startswith('> '):
            out.append(f'<blockquote>{_inline(ln[2:].strip())}</blockquote>')
            body_weight += 2; i += 1; continue
        if ln.startswith('|'):
            tbl = []
            while i < len(lines) and lines[i].startswith('|'):
                tbl.append(lines[i]); i += 1
            html, rc = _render_table(tbl)
            out.append(html); body_weight += max(rc, 1) * 1.2
            continue
        # 번호 리스트 감지 → step 변환 시도
        if re.match(r'^\d+\.\s', ln):
            block = []
            j = i
            while j < len(lines) and re.match(r'^\d+\.\s', lines[j]):
                block.append(lines[j]); j += 1
            steps = _detect_steps(block)
            if steps:
                out.append(_render_steps(steps))
                body_weight += len(steps) * 1.4
                i = j; continue
            # 일반 ordered list
            out.append('<ol>')
            for b in block:
                out.append('<li>' + _inline(re.sub(r'^\d+\.\s+', '', b).strip()) + '</li>')
            out.append('</ol>')
            body_weight += len(block) * 0.8
            i = j; continue
        if re.match(r'^[-*]\s', ln):
            out.append('<ul>')
            while i < len(lines) and re.match(r'^[-*]\s', lines[i]):
                out.append('<li>' + _inline(re.sub(r'^[-*]\s+', '', lines[i]).strip()) + '</li>')
                body_weight += 0.7; i += 1
            out.append('</ul>'); continue
        # 단락
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '>', '|', '-', '*')) and not re.match(r'^\d+\.', lines[i]):
            para.append(lines[i].strip()); i += 1
        if para:
            out.append('<p>' + _inline(' '.join(para)) + '</p>')
            body_weight += len(' '.join(para)) / 200.0
        else:
            i += 1
    return '\n'.join(out), body_weight

# ── 섹션 분리 ─────────────────────────────────────────────────────
def split_sections(md):
    # YAML 프론트매터(--- ... ---) 제거 + title 폴백 추출 (2026-07-15)
    #   렌더러가 raw 노트(프론트매터 포함, # H1 없음)를 받아도 제목이 "리포트"로 떨어지거나
    #   "title:" 줄이 본문/부제로 노출되지 않게 한다.
    fm_title = ""
    m = re.match(r'^﻿?---[ \t]*\r?\n(.*?\n)?---[ \t]*\r?\n', md, re.S)
    if m:
        tm = re.search(r'(?m)^[ \t]*title:[ \t]*(.+?)[ \t]*$', m.group(1) or "")
        if tm:
            fm_title = tm.group(1).strip().strip('"\'')
        md = md[m.end():]
    title, sections, t, b = "", [], None, []
    lead = ""  # 첫 블록쿼트 또는 첫 단락
    pre_h2_lines = []
    for ln in md.splitlines():
        if ln.startswith('# ') and not ln.startswith('## ') and not title:
            title = ln[2:].strip(); continue
        if ln.startswith('## '):
            if t is not None:
                sections.append((t, '\n'.join(b)))
            t, b = ln[3:].strip(), []
        elif t is not None:
            b.append(ln)
        else:
            pre_h2_lines.append(ln)
    if t is not None:
        sections.append((t, '\n'.join(b)))

    # lead 추출: 첫 ## 섹션 이전의 blockquote 우선, 없으면 첫 단락
    for ln in pre_h2_lines:
        s = ln.strip()
        if s.startswith('> '):
            lead = s[2:].strip(); break
    if not lead:
        for ln in pre_h2_lines:
            s = ln.strip()
            if s and not s.startswith(('#', '|', '-', '*', '>')) and not re.match(r'^\d+\.', s):
                lead = s; break
    if not title:
        title = fm_title   # # H1 없으면 프론트매터 title 사용
    return title, lead, sections

# ── 메타 섹션 필터 ─────────────────────────────────────────────────
_META_TITLES = {'출처', '참고자료', 'References', 'Reference', '비주얼 리포트', 'Visual Report'}
def _is_meta(h):
    h = h.strip()
    if h in _META_TITLES:
        return True
    if '완성도 검증' in h or 'V1~V8' in h or 'V1-V8' in h:
        return True
    if h.lower().startswith('sources'):
        return True
    return False

# ── 섹션 → 카드 span 결정 (12-grid) ───────────────────────────────
def _decide_span(weight, has_table, has_steps, idx, total):
    """카드 span(4|6|12) 결정: 무거우면 12, 가벼우면 6, 매우 가벼우면 4."""
    if has_table and weight > 6:
        return 12
    if has_steps and weight > 5:
        return 12
    if weight >= 8:
        return 12
    if weight >= 3:
        return 6
    return 6  # 기본 2단

# ── CSS ────────────────────────────────────────────────────────────
# AI Daily YouTube Summaries theme.
# ⚠️ accent 파생색은 use-site에서 var(--accent) 직접 사용(간접참조 :root 동결 함정 회피).
CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{
  /* AI Daily · daylight neutral */
  --canvas:#EEF2F6;--canvas-top:#EAF1F8;--bg:#FFFFFF;--surface:#F7F9FB;--box-bg:#F7F9FB;
  --text:#16202B;--ink-700:#3F4A56;--muted:#76818E;--border:#E7ECF1;
  /* 카테고리 식별색(기본=공학·테크). body.cat-*에서 재정의 */
  --accent:#0E9E7E;--accent-d:#0B7A60;--accent-light:#E3F6F0;--accent-ink:#0B6B54;
  /* 시맨틱(카테고리 무관 고정) */
  --up:#12A150;--dn:#E5484D;--fill:#3F4A56;
}
body.cat-tech{--accent:#0E9E7E;--accent-d:#0B7A60;--accent-light:#E3F6F0;--accent-ink:#0B6B54}
body.cat-econ{--accent:#2E6BF0;--accent-d:#1F50C4;--accent-light:#E7EFFE;--accent-ink:#1B47AE}
body.cat-hub{--accent:#6A4BE0;--accent-d:#5236C2;--accent-light:#EEEAFD;--accent-ink:#4A30B0}
html{font-size:16px;-webkit-text-size-adjust:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Noto Sans KR","Apple SD Gothic Neo","Segoe UI",sans-serif;
  color:var(--text);background:linear-gradient(180deg,var(--canvas-top),var(--canvas) 280px);
  background-color:var(--canvas);line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden;
}
.page{max-width:1180px;margin:0 auto;padding:24px 20px 60px;}
@media (max-width:768px){.page{padding:14px 10px 40px}}

/* ─ Header (카테고리 accent 그라데이션 = 그 글의 주제색) ─ */
.hdr{
  background:linear-gradient(135deg,var(--accent-d),var(--accent));color:#fff;
  border-radius:16px;padding:32px 36px 26px;margin-bottom:16px;
}
.hdr-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;font-size:12.5px;letter-spacing:.06em;font-weight:700}
.hdr-meta .chip{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.34);padding:5px 11px;border-radius:999px;color:#fff}
.hdr-meta .chip.brand{background:#fff;color:var(--accent-ink);border-color:#fff}
.hdr-meta .chip.brand .dot{width:7px;height:7px;border-radius:50%;background:var(--accent)}
.hdr-meta .ey{color:rgba(255,255,255,.85);font-weight:700;text-transform:uppercase;letter-spacing:.12em}
.hdr h1{font-size:32px;font-weight:900;line-height:1.22;letter-spacing:-.02em;margin:16px 0 12px;color:#fff;word-break:keep-all}
.hdr .lead{font-size:16px;line-height:1.6;color:rgba(255,255,255,.94);max-width:920px;word-break:keep-all}
@media (max-width:640px){
  .hdr{padding:22px 20px 18px}
  .hdr h1{font-size:24px;margin:12px 0 8px}
  .hdr .lead{font-size:14.5px}
}

/* ─ Video (영상 재생) ─ */
.video-wrap{position:relative;width:100%;padding-top:56.25%;background:#000;border:1px solid var(--border);border-radius:14px;overflow:hidden;margin-bottom:16px}
.video-wrap iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.video-cta{margin-bottom:16px}
.play-btn{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:#fff;font-weight:800;font-size:15px;padding:11px 20px;border-radius:999px;text-decoration:none}
.play-btn:hover{background:var(--accent-d)}

/* ─ Grid ─ */
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
.card{
  background:var(--bg);border:1px solid var(--border);border-radius:14px;
  padding:18px 22px;display:flex;flex-direction:column;min-width:0;
  box-shadow:0 1px 4px rgba(16,32,43,.05);
}
.card.s4{grid-column:span 4}
.card.s6{grid-column:span 6}
.card.s12{grid-column:span 12}
@media (max-width:900px){
  .card.s4,.card.s6{grid-column:span 12}
}

/* ─ Card header ─ */
.card>h2{
  font-size:16px;font-weight:800;color:var(--accent-ink);
  display:flex;align-items:center;gap:9px;
  padding-bottom:9px;margin-bottom:12px;border-bottom:2px solid var(--border);
  word-break:keep-all
}
.card>h2::before{
  content:"";width:5px;height:18px;background:var(--accent);border-radius:2px;flex:none
}
.card>h2 .seq{
  font-size:11px;font-weight:800;color:#fff;background:var(--accent);
  padding:3px 8px;border-radius:6px;letter-spacing:.04em
}

/* ─ Typography in card ─ */
.card h3{font-size:14px;font-weight:800;color:var(--accent-ink);margin:10px 0 4px}
.card p{font-size:14px;line-height:1.65;margin:5px 0;word-break:keep-all}
.card ul,.card ol{margin:4px 0 4px 19px}
.card li{font-size:14px;line-height:1.6;margin:5px 0;word-break:keep-all}
.card blockquote{
  border:1px solid var(--border);border-left:3px solid var(--accent);background:var(--box-bg);
  border-radius:10px;padding:10px 14px;font-size:13.5px;line-height:1.6;
  color:var(--text);margin:7px 0
}
.card code{background:var(--surface);padding:1px 5px;border-radius:4px;font-size:.92em;overflow-wrap:anywhere}
.card a{color:var(--accent-ink);text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:1px;word-break:break-all;overflow-wrap:anywhere}
.card a:hover{color:var(--accent-d)}
.card strong{color:var(--text)}

/* ─ Tables (Deep 헤더 + 제브라) ─ */
.tbl-wrap{
  overflow-x:auto;border:1px solid var(--border);border-radius:10px;margin:6px 0
}
table{width:100%;border-collapse:collapse;font-size:13.5px;background:#fff}
th{
  background:var(--accent-d);color:#fff;padding:8px 11px;text-align:left;
  font-weight:700;font-size:12.5px;letter-spacing:.02em;word-break:keep-all
}
td{
  padding:7px 11px;border-bottom:1px solid var(--border);
  vertical-align:top;line-height:1.55;word-break:keep-all
}
td:first-child{font-weight:700;color:var(--text);white-space:nowrap}
tr:last-child td{border-bottom:none}
tr:nth-child(even) td{background:var(--surface)}

/* ─ Step flow (infographic) ─ */
.steps{display:flex;flex-direction:column;gap:8px;margin:6px 0}
.step{
  display:flex;align-items:flex-start;gap:11px;
  background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:11px 13px
}
.step .snum{
  flex:none;width:32px;height:32px;border-radius:8px;
  background:var(--accent);color:#fff;font-weight:800;font-size:14px;
  display:flex;align-items:center;justify-content:center
}
.step .sbody{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1}
.step .sbody b{font-size:14px;color:var(--text);line-height:1.4;word-break:keep-all}
.step .sbody span{font-size:13px;color:var(--text);line-height:1.55;word-break:keep-all}

/* ─ Colors / states ─ */
.up{color:var(--up);font-weight:700}
.dn{color:var(--dn);font-weight:700}
.hl{color:var(--accent);font-weight:700}

/* ─ Infographic blocks (bars/kpi/donut/timeline) ─ */
.ig-bars{display:flex;flex-direction:column;gap:7px;margin:8px 0}
.ig-bar{display:grid;grid-template-columns:minmax(80px,30%) 1fr auto;align-items:center;gap:10px;font-size:13.5px}
.igb-l{font-weight:700;color:var(--text);word-break:keep-all}
.igb-track{height:15px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.igb-fill{display:block;height:100%;background:var(--accent)}
.igb-v{font-weight:700;color:var(--text);white-space:nowrap}
.ig-kpis{display:flex;flex-wrap:wrap;gap:11px;margin:8px 0}
.ig-kpi{flex:1;min-width:124px;background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:13px 16px;display:flex;flex-direction:column;gap:3px}
.igk-v{font-size:27px;font-weight:900;color:var(--accent-ink);line-height:1.1;font-variant-numeric:tabular-nums}
.igk-l{font-size:12.5px;color:var(--muted);font-weight:600}
.ig-donuts{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0}
.ig-donut{display:flex;flex-direction:column;align-items:center;gap:6px}
.igd-ring{width:78px;height:78px;border-radius:50%;display:flex;align-items:center;justify-content:center;position:relative}
.igd-ring::after{content:"";position:absolute;width:52px;height:52px;border-radius:50%;background:var(--bg)}
.igd-num{position:relative;z-index:1;font-size:16px;font-weight:800;color:var(--text);font-variant-numeric:tabular-nums}
.igd-l{font-size:13px;color:var(--text);font-weight:600;text-align:center;max-width:108px;word-break:keep-all}
.ig-timeline{display:flex;flex-direction:column;margin:8px 0 8px 5px;border-left:2px solid var(--border);padding-left:15px}
.ig-tl{position:relative;padding:6px 0}
.igt-dot{position:absolute;left:-21px;top:11px;width:10px;height:10px;border-radius:50%;background:var(--accent)}
.igt-t{font-weight:800;color:var(--text);font-size:13.5px;margin-right:8px}
.igt-x{font-size:13.5px;color:var(--text);line-height:1.55}
.ig-raw{font-size:13.5px;color:var(--text);white-space:pre-wrap;line-height:1.6}

/* ─ Footer ─ */
.foot{
  margin-top:22px;padding:14px 18px;text-align:center;
  font-size:12.5px;color:var(--muted);
  border:1px solid var(--border);border-radius:12px;background:#fff
}
.foot .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:7px;vertical-align:middle}

@media (max-width:640px){
  .grid{gap:11px}
  .card{padding:14px 15px;border-radius:12px}
  .card>h2{font-size:15px}
  .card p,.card li,.card h3{font-size:14.5px}
  table{font-size:13px}
  th{padding:7px 9px;font-size:12px}
  td{padding:6px 9px}
  td:first-child{white-space:normal}
  .hdr-meta{font-size:11.5px;gap:7px}
}
@media print{
  body{background:#fff}.page{padding:14px}
  .card,.foot,.tbl-wrap,.video-wrap{break-inside:avoid}
  .hdr{break-after:avoid}
}
"""

# ── 빌드 ───────────────────────────────────────────────────────────
def build_report(md, eyebrow="", badge="", title_override="", brand="", footer="",
                 video_url="", category="tech", show_section_numbers=True):
    title, lead, sections = split_sections(md)
    sections = [(h, b) for (h, b) in sections if not _is_meta(h)]
    if title_override:
        title = title_override
    if not title:
        title = "리포트"
    # External channel configuration uses economy/community aliases.
    # (안 하면 "economy"가 조용히 tech(녹색)로 강등 → 경제 글이 녹색으로 나옴).
    category = {"economy": "econ", "community": "hub"}.get(category, category)
    cat = category if category in ("tech", "econ", "hub") else "tech"

    # 헤더 메타
    parts = []
    if brand:
        parts.append(f'<span class="chip brand"><span class="dot"></span>{esc(brand)}</span>')
    # eyebrow: "YOUTUBE SUMMARIES · 2026-07-02 · 채널명"
    if eyebrow:
        parts.append(f'<span class="ey">{esc(eyebrow)}</span>')
    if badge:
        parts.append(f'<span class="chip">{esc(badge)}</span>')
    hdr_meta = '<div class="hdr-meta">' + ''.join(parts) + '</div>'

    hdr = (
        f'<header class="hdr">{hdr_meta}'
        f'<h1>{esc(title)}</h1>'
        + (f'<p class="lead">{_inline(lead)}</p>' if lead else '')
        + ('<p class="report-scope" style="font-size:12px;line-height:1.7;opacity:.75">영상 발화자의 견해·경험을 원문에 근거해 정리한 요약입니다.</p>' if video_url else '')
        + ''.join('<p class="report-scope" style="font-size:12px;line-height:1.7;opacity:.75">'+esc(line[2:].strip())+'</p>' for line in md.splitlines() if line.startswith('> 분석 범위:'))
        + '</header>'
    )

    # 영상 재생 블록(본문 끝·풋터 바로 위에 배치 — 2026-07-05)
    video = _video_block(video_url)

    # 카드 (목차 제거 — 2026-07-02)
    cards = []
    for idx, (h, body) in enumerate(sections, 1):
        h = _clean_head(h)  # 소제목에 링크주소 노출 금지
        m = re.match(r'^(\d+)\.\s*(.+)$', h)
        if m:
            seq = f"{int(m.group(1)):02d}"
            head_text = m.group(2)
        else:
            seq = f"{idx:02d}"
            head_text = h
        anchor = f"s{idx}"
        rendered, wt = md_body(body)
        has_table = 'tbl-wrap' in rendered
        has_steps = 'steps' in rendered
        span = _decide_span(wt, has_table, has_steps, idx, len(sections))
        number = f'<span class="seq">{seq}</span>' if show_section_numbers else ''
        cards.append(
            f'<section class="card s{span}" id="{anchor}">'
            f'<h2>{number}{esc(head_text)}</h2>'
            f'{rendered}'
            '</section>'
        )

    grid = '<main class="grid">' + ''.join(cards) + '</main>'
    foot = f'<div class="foot"><span class="dot"></span>{esc(footer or brand or "")}</div>' if (footer or brand) else ''

    # 목록으로 링크 (모든 페이지 필수 — 템플릿 룰. A의 후처리에 의존하지 않고 렌더러가 항상 삽입)
    to_list = ('<div id="to-list" style="text-align:center;margin:32px 0 8px">'
               '<a href="./" style="display:inline-block;padding:10px 22px;border-radius:999px;'
               'border:1px solid currentColor;color:inherit;text-decoration:none;font-size:14px;'
               'opacity:.72">← 목록으로</a></div>')

    desc = (lead or title)[:150]
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="description" content="{esc(desc)}">'
        f'<title>{esc(title)}</title>'
        f'<style>{CSS}</style>'
        '</head>'
        f'<body class="cat-{cat}">'
        f'<div class="page">{hdr}{grid}{video}{foot}{to_list}</div>'
        '</body></html>'
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eyebrow", default="")
    ap.add_argument("--badge", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--brand", default="")
    ap.add_argument("--footer", default="")
    ap.add_argument("--video-url", dest="video_url", default="")
    ap.add_argument("--hide-section-numbers", action="store_true")
    ap.add_argument("--category", default="tech",
                    help="주제 색: tech(공학·테크/기본) | econ(경제·마켓) | hub(AI·데이터)")
    a = ap.parse_args()
    md = open(a.inp, encoding="utf-8").read()
    html = build_report(md, eyebrow=a.eyebrow, badge=a.badge,
                        title_override=a.title, brand=a.brand, footer=a.footer,
                        video_url=a.video_url, category=a.category,
                        show_section_numbers=not a.hide_section_numbers)
    with open(a.out, "w", encoding="utf-8") as output:
        output.write(html)
    n = html.count('class="card')
    print(f"[youtube_summaries] {a.out} — single-page report, {n} section cards, cat={a.category}, video={'y' if a.video_url else 'n'}")

if __name__ == "__main__":
    main()
