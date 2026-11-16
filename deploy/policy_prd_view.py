"""Style B policy workbench renderer; content and downloads stay unchanged."""
import html
import re
from pathlib import Path

ASSETS=Path(__file__).with_name('policy-prd-assets')

def inline(value):
    parts=re.split(r'(`[^`]+`|\*\*[^*]+\*\*)',value)
    return ''.join('<code>'+html.escape(p[1:-1])+'</code>' if p.startswith('`') else '<strong>'+html.escape(p[2:-2])+'</strong>' if p.startswith('**') else html.escape(p) for p in parts)

def fragment(lines):
    out=[];code=[];language=None;table=[];items=[]
    def flush():
        if table:
            headers=table[0];out.append('<table class="qb-table"><thead><tr>'+''.join('<th scope="col">'+inline(c)+'</th>' for c in headers)+'</tr></thead><tbody>')
            for row in table[1:]:out.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            out.append('</tbody></table>');table.clear()
        if items:out.append('<ul>'+''.join('<li>'+inline(x)+'</li>' for x in items)+'</ul>');items.clear()
    for line in lines:
        if line.startswith('```'):
            if language is not None:
                out.append('<pre tabindex="0" aria-label="'+html.escape(language or '원문 코드')+'"><code>'+html.escape('\n'.join(code))+'</code></pre>');language=None;code=[]
            else:flush();language=line[3:]
            continue
        if language is not None:code.append(line);continue
        if line.startswith('|'):
            cells=[c.strip() for c in line.strip().strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?',x) for x in cells):table.append(cells)
            continue
        if table:flush()
        if line.startswith('- '):items.append(line[2:]);continue
        if items:flush()
        match=re.match(r'^(#{1,6}) (.*)',line)
        if match:out.append('<h3>'+inline(match[2])+'</h3>')
        elif line.strip():out.append('<p>'+inline(line)+'</p>')
    flush()
    if language is not None:out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>')
    return ''.join(out)

def render(md):
    sections=[];title='문서 개요';lines=[];incode=False
    for line in md.splitlines():
        if line.startswith('```'):incode=not incode
        if not incode and line.startswith('## '):
            if lines:sections.append((title,lines))
            title=line[3:];lines=[]
        elif not sections and line.startswith('# '):continue
        else:lines.append(line)
    if lines:sections.append((title,lines))
    nav=[];articles=[]
    for i,(title,lines) in enumerate(sections):
        sid=f'policy-{i:02d}'
        nav.append(f'<a class="qb-nav" href="#{sid}" data-section="{sid}" title="{html.escape(title,quote=True)}"><span>{inline(title)}</span><span class="qb-count">{i+1:02d}</span></a>')
        articles.append(f'<section id="{sid}" class="policy-section" data-title="{html.escape(title,quote=True)}" tabindex="-1"><h2>{inline(title)}</h2>'+fragment(lines)+'</section>')
    status='내용을 선택하면 해당 정책을 표시합니다.'
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AI Daily · 정책 PRD</title><link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="bundle.css"><link rel="stylesheet" href="policy.css"><script src="policy.js" defer></script></head><body>
<a class="skip" href="#policy-main">본문으로 이동</a>
<header class="page-head"><div><span class="eyebrow">AI Daily</span><h1>운영 · 정책 PRD</h1></div><button class="qb-btn" id="inspector-open" aria-controls="policy-inspector" aria-expanded="false">문서 정보 보기</button></header>
<div class="qb-shell split">
<nav class="qb-side" aria-label="정책 목차"><div class="grp">정책 · 목차</div>'''+''.join(nav)+'''</nav>
<main class="qb-main" id="policy-main"><div class="qb-head"><span id="selection-title">정책 · 전체 내용</span><span class="qb-kbd">J K 이동</span></div><div class="document">'''+''.join(articles)+'''</div></main>
<aside class="qb-inspector" id="policy-inspector" aria-label="문서 정보" tabindex="-1"><div class="qb-head"><button class="qb-btn qb-back" id="inspector-close">목록으로</button><h2>문서 · 정보</h2></div><div class="body"><dl><dt>현재 범위</dt><dd id="inspector-section">전체 정책</dd><dt>접근</dt><dd>관리자 인증 · type1</dd><dt>자동 갱신</dt><dd>변경 감지 주기 60초</dd><dt>원본</dt><dd>정책 · 설정 · 실행 코드</dd></dl><p>정책 설명과 현재 설정·실행 상태를 함께 확인합니다. 의미 검토가 필요한 코드 변경은 문서에 표시합니다.</p><div class="downloads"><a class="qb-btn primary" href="PRD.md" download>PRD 저장</a><a class="qb-btn" href="policy-snapshot.json" download>설정 저장</a><button class="qb-btn" id="print-document">문서 인쇄</button></div><div class="reference"><h3>검토 · 기준</h3><p>B안 워크벤치</p><p>정책 원문과 다운로드 파일의 전체 내용을 유지합니다.</p></div></div></aside>
</div><div class="sr-only" role="status" id="policy-status">'''+status+'''</div></body></html>'''
