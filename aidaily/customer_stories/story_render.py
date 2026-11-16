"""Public, escaped presentation for version-two editorial customer stories.

This module displays supplied evidence; a valid citation URL does not establish
factual truth. Collection, editorial review and publication stay with the caller.
"""
from __future__ import annotations

import hashlib
import html
from urllib.parse import urlsplit

from aidaily.customer_stories.pipeline import public_source_label, public_story_text


def _text(value):
    return html.escape(public_story_text(str(value or '')), quote=True)


def safe_url(value):
    """Allow absolute HTTP sources, excluding credentials and control characters."""
    if not isinstance(value, str) or value != value.strip() or any(ord(c) < 33 for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return ''
        parsed.port  # reject malformed port
    except ValueError:
        return ''
    return value


def story_anchor(story_id):
    """Stable anchor independent of display order and private identifier contents."""
    return 'story-' + hashlib.sha256(str(story_id).encode()).hexdigest()[:20]


def _link(url, label):
    target = safe_url(url)
    return (f'<a href="{html.escape(target, quote=True)}" rel="noopener noreferrer">{_text(label) or "출처 보기"}</a>'
            if target else '')


CSS = '''
:root{--bg:#ffffff;--line:#e6e9ee;--text:#141c27;--text-2:#4a5566;--text-3:#6b7685;--accent:#1e6ef4;--panel:#f5f7fa;--space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;--space-5:24px;--space-6:32px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Pretendard,system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;font-size:15px;line-height:1.8}a{color:var(--accent);text-underline-offset:4px;overflow-wrap:anywhere}a:focus-visible{outline:2px solid var(--accent);outline-offset:4px}.shell{display:grid;grid-template-columns:220px minmax(0,1fr) 240px;max-width:1440px;margin:auto;min-height:100vh}.side{background:var(--panel);padding:var(--space-5);font-size:13px}.side a{display:block;padding:var(--space-2) 0}.main{padding:var(--space-6);min-width:0}.context{padding:var(--space-5);color:var(--text-2);font-size:13px;border-left:1px solid var(--line)}header{padding-bottom:var(--space-5);border-bottom:1px solid var(--line)}h1{font-size:24px;line-height:1.5;margin:var(--space-2) 0}h2{font-size:21px;line-height:1.6;margin:0 0 var(--space-4)}h3{font-size:16px;line-height:1.6;margin:var(--space-5) 0 var(--space-2)}p{margin:var(--space-2) 0}.meta{color:var(--text-3);font-size:12px}.overview{color:var(--text-2)}article{padding:var(--space-6) 0;border-bottom:1px solid var(--line);scroll-margin-top:var(--space-4);overflow-wrap:anywhere}ul{padding-left:20px;margin:var(--space-2) 0}li{padding:var(--space-1) 0}.attribution{display:block;color:var(--text-3);font-size:12px}.empty{color:var(--text-2)}.skip{position:absolute;left:-10000px}.skip:focus{left:16px;top:16px;background:var(--bg);padding:12px}
@media(prefers-color-scheme:dark) and (min-width:601px){:root{--bg:#0f141b;--line:#232c38;--text:#e8edf3;--text-2:#aab4c2;--text-3:#8592a3;--accent:#5aa2ff;--panel:#171e28}}
@media(max-width:900px){.shell{grid-template-columns:180px minmax(0,1fr)}.context{grid-column:2;border-left:0;border-top:1px solid var(--line)}}
@media(max-width:600px){.shell{display:block}.side{background:var(--bg);padding:var(--space-4);border-bottom:1px solid var(--line)}.side a{min-height:44px;padding:8px 0}.main,.context{padding:var(--space-4)}.context{border-top:1px solid var(--line)}h1{font-size:22px}.main a{display:inline-block;min-height:44px;padding:8px 0}body{font-size:16px}h2{font-size:20px}}
'''


def render_story_report(report, date, *, archive_href='index.html'):
    """Render at most two stories with cited facts and attributed experiences.

    Caller supplies editorial text and validated evidence IDs. Unsupported
    timeline rows are omitted. This renderer makes no factual/privacy certification.
    """
    if report.get('schema_version', 2) != 2:
        raise ValueError('Expected story report schema version 2')
    items = report.get('items') or []
    if not isinstance(items, list) or len(items) > 2:
        raise ValueError('Story report must contain zero to two items')
    ids = [str(item.get('story_id', '')) for item in items]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('Stories require unique stable story_id values')
    if archive_href not in ('index.html', '../uservoice/index.html'):
        raise ValueError('Unsupported archive path')
    nav, articles = [], []
    for item in items:
        anchor = story_anchor(item['story_id'])
        title = _text(item.get('issue'))
        nav.append(f'<a href="#{anchor}">{title}</a>')
        facts = []
        for row in item.get('background') or []:
            link = _link(row.get('url'), row.get('label') or '공개 자료')
            if link and row.get('text'):
                facts.append(f'<li>{_text(row["text"])} {link}</li>')
        fact_html = ('<ul>' + ''.join(facts) + '</ul>' if facts else
                     '<p class="empty">확인된 공개 배경 자료가 없습니다.</p>')
        voices = []
        for row in item.get('voices') or []:
            if row.get('text'):
                source = public_source_label(str(row.get('source') or ''))
                attribution = ' · '.join(_text(value) for value in (source, row.get('date')) if value)
                voices.append(f'<li>{_text(row["text"])}<span class="attribution">{attribution}</span></li>')
        voice_html = '<ul>' + ''.join(voices) + '</ul>' if voices else '<p class="empty">확인 가능한 사용자 경험이 없습니다.</p>'
        timeline = []
        for row in item.get('timeline') or []:
            if row.get('evidence_ids') and row.get('text'):
                timeline.append(f'<li><strong>{_text(row.get("stage"))}</strong> {_text(row["text"])}</li>')
        timeline_html = '<h3>이야기의 흐름</h3><ul>' + ''.join(timeline) + '</ul>' if timeline else ''
        commentary = f'<h3>기자의 짚어보기</h3><p>{_text(item["commentary"])}</p>' if item.get('commentary') else ''
        links = [_link(row.get('url'), row.get('label')) for row in item.get('related_links') or []]
        links = [link for link in links if link]
        related = '<h3>관련 자료</h3><ul>' + ''.join('<li>' + link + '</li>' for link in links) + '</ul>' if links else ''
        articles.append(f'<article id="{anchor}" aria-labelledby="{anchor}-title"><h2 id="{anchor}-title">{title}</h2><h3>확인된 사실</h3>{fact_html}<h3>사용자 목소리</h3>{voice_html}{timeline_html}{commentary}{related}</article>')
    content = ''.join(articles) or '<p class="empty" role="status">선정된 이야기가 없습니다. 지난 사용기를 확인할 수 있습니다.</p>'
    if report.get('edition_note'):
        content += f'<p class="meta">{_text(report["edition_note"])}</p>'
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_text(report.get('title') or '고객 사용기')}</title><style>{CSS}</style></head><body><a class="skip" href="#main">본문으로 이동</a><div class="shell"><nav class="side" aria-label="사용기 탐색"><a href="{archive_href}">지난 사용기 보기</a>{''.join(nav)}</nav><main class="main" id="main"><header><p class="meta">VAAX · 고객 사용기 · {_text(date)}</p><h1>{_text(report.get('title') or '고객 사용기')}</h1><p class="overview">{_text(report.get('overview'))}</p></header>{content}</main><aside class="context" aria-label="읽기 안내"><p>공개 자료로 확인한 사실과 사용자의 경험을 함께 전합니다.</p><p>사용 조건과 관찰 범위를 함께 읽어 주세요.</p></aside></div></body></html>'''
