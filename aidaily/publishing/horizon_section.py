"""Read-only, source-attributed Horizon pilot section for the existing daily page."""
from __future__ import annotations
import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from aidaily import config

ROOT = config.DATA_ROOT / 'ai_news' / 'horizon'
STATUS = {'complete', 'partial', 'pending', 'running', 'failed', 'invalid'}
CSS = '''
.horizon-briefing{margin-top:26px;overflow-wrap:anywhere}
.horizon-briefing h2,.horizon-briefing h3{margin:0}
.horizon-briefing a:focus-visible,.horizon-briefing summary:focus-visible{outline:2px solid currentColor;outline-offset:4px}
.horizon-briefing .horizon-items{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:0 26px}
.horizon-briefing article{padding:16px 0;border-bottom:1px solid var(--horizon-line)}
.horizon-briefing article h3{font-size:14px;font-weight:750;line-height:1.55;letter-spacing:-.012em}
.horizon-briefing article ul{margin:9px 0 0;padding-left:17px;font-size:14px;line-height:1.8}
.horizon-briefing article li+li{margin-top:5px}
.horizon-briefing .horizon-meta{font-size:11px;line-height:1.8;margin-top:5px}
.horizon-briefing .horizon-reason{font-size:12px;line-height:1.8;margin:9px 0 0}
.horizon-briefing .horizon-sources{font-size:11.5px;line-height:1.9;padding-top:12px}
@media(max-width:640px){.horizon-briefing .horizon-items{grid-template-columns:1fr}.horizon-briefing article ul{font-size:15px}.horizon-briefing article h3{font-size:15.5px}.horizon-briefing .horizon-meta,.horizon-briefing .horizon-sources{font-size:12.5px}.horizon-briefing .horizon-reason{font-size:14px}}
'''

def safe_url(value):
    if not isinstance(value, str) or value != value.strip() or any(ord(c) < 33 for c in value): return ''
    try:
        p = urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None:return ''
        p.port
    except ValueError:return ''
    return value

def clean_text(value):
    return value.strip() if isinstance(value, str) else ''

def normalize_edition(value, date):
    if not isinstance(value, dict) or value.get('date') != date or value.get('status') not in STATUS:
        raise ValueError('Invalid Horizon edition identity/status')
    result = {'date': date, 'status': value['status'], 'pilot': {}, 'items': [], 'sources': [], 'metrics': {}}
    for key in ('start', 'end'):
        v = (value.get('pilot') or {}).get(key)
        if isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):result['pilot'][key] = v
    items = value.get('items') or []
    if not isinstance(items, list) or len(items) > 10:raise ValueError('Invalid Horizon items')
    seen = set()
    for row in items:
        if not isinstance(row, dict):raise ValueError('Invalid Horizon item')
        url = safe_url(row.get('url')); title = clean_text(row.get('title'))
        if not url or not title or url in seen:raise ValueError('Invalid/duplicate Horizon source')
        seen.add(url)
        bullets = row.get('bullets') or []
        if not isinstance(bullets, list) or not bullets or not all(isinstance(x, str) and x.strip() for x in bullets):raise ValueError('Missing Horizon explanation')
        result['items'].append({'id': clean_text(row.get('id')) or str(len(seen)), 'title': title, 'url': url,
            'source_name': clean_text(row.get('source_name')) or urlsplit(url).hostname,
            'source_type': clean_text(row.get('source_type')), 'published_at': clean_text(row.get('published_at')),
            'published_at_note': clean_text(row.get('published_at_note')), 
            'reason': clean_text(row.get('reason')), 'bullets': [x.strip() for x in bullets]})
    for row in value.get('sources') or []:
        if not isinstance(row, dict):continue
        name = clean_text(row.get('name')); url = safe_url(row.get('url'))
        if not name or not url:continue
        count = row.get('candidate_count')
        result['sources'].append({'name': name, 'url': url, 'type': clean_text(row.get('type')), 'status': clean_text(row.get('status')),
                                 'candidate_count': count if type(count) is int and count >= 0 else None})
    for key in ('candidate_count', 'selected_count', 'new_count', 'overlap_count', 'source_count', 'lookback_hours'):
        v = (value.get('metrics') or {}).get(key)
        if type(v) is int and v >= 0:result['metrics'][key] = v
    if result['status'] == 'complete' and any(x['status'] in ('unavailable', 'failed', 'error') for x in result['sources']):result['status'] = 'partial'
    return result

def load_pilot(root=None):
    root = Path(root) if root is not None else config.DATA_ROOT / 'ai_news' / 'horizon'
    try:
        data = json.loads((root / 'settings.json').read_text())['pilot']
        return {k: dt.date.fromisoformat(data[k]).isoformat() for k in ('start', 'end')}
    except (OSError, ValueError, TypeError, KeyError):return {}

def load_editions(root=None):
    """Never let an optional pilot file prevent the existing daily rendering."""
    root = Path(root) if root is not None else config.DATA_ROOT / 'ai_news' / 'horizon'; editions = {}
    for path in (root / 'editions').glob('????-??-??.json'):
        date = path.stem
        try:dt.date.fromisoformat(date)
        except ValueError:continue
        try:
            editions[date] = normalize_edition(json.loads(path.read_text()), date)
        except (OSError, ValueError, TypeError):
            editions[date] = {'date': date, 'status': 'invalid', 'items': [], 'sources': [], 'metrics': {}, 'pilot': {}}
    # Pending jobs are status only; never publish raw candidate text or internal logs.
    for path in (root / 'runs').glob('????-??-??.json'):
        if path.stem in editions:continue
        try:
            dt.date.fromisoformat(path.stem)
            data = json.loads(path.read_text()); status = data.get('status', '')
            if status in ('fetching', 'scoring', 'deduplicating', 'fetching_original', 'enriching'):status = 'running'
            if status in ('collection_unavailable', 'review_required'):status = 'failed'
            if status in ('pending', 'running', 'failed'):
                editions[path.stem] = normalize_edition({'date': path.stem, 'status': status, 'items': [], 'sources': data.get('sources') or [], 'metrics': {'candidate_count': len(data.get('candidates') or [])}, 'pilot': data.get('pilot') or {}}, path.stem)
        except (OSError, ValueError, TypeError):pass
    return editions

def _published(value):
    if not value:return ''
    try:
        date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is not None:date = date.astimezone(dt.timezone(dt.timedelta(hours=9)))
        return date.strftime('%m.%d %H:%M') + (' KST' if date.tzinfo else '')
    except ValueError:return value[:40]

def render_section(edition, date, tokens, pilot=None):
    C = tokens['color']; tone = C['accent']['tech']; ink = C['text']['tech.ink']; dim = C['text']['tech.dim']; muted = C['text']['tech.muted']; line = C['line']['tech']
    e = html.escape
    valid = isinstance(edition, dict) and edition.get('date') == date
    data = edition if valid else {'status': 'absent', 'items': [], 'sources': [], 'metrics': {}, 'pilot': {}}
    pilot = data.get('pilot') or pilot or {}
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):pilot_label = '__HORIZON_PILOT_LABEL__'
    elif pilot.get('start') and date < pilot['start']:pilot_label = '시범 시작 전'
    elif pilot.get('end') and date > pilot['end']:pilot_label = '시범 운영 종료'
    else:pilot_label = '시범 운영'
    status = data.get('status', 'invalid'); items = data.get('items') or []
    if status not in ('complete', 'partial'):items = []
    messages = {'absent': '이 날짜의 Horizon 브리핑이 없습니다.', 'running': '이 날짜의 Horizon 브리핑을 준비하고 있습니다.',
                'pending': '자료 선별을 진행하고 있습니다. 준비되는 대로 반영합니다.', 'failed': '이 날짜의 Horizon 브리핑을 완성하지 못했습니다.',
                'invalid': '이 날짜의 Horizon 브리핑을 불러오지 못했습니다.'}
    body = []
    for row in items:
        url = safe_url(row.get('url'))
        if not url:continue
        meta = ['원문 · ' + e(urlsplit(url).hostname), '수집 · ' + e(row.get('source_name') or urlsplit(url).hostname)]
        if row.get('published_at'):
            note = row.get('published_at_note') or ('Hacker News 게시 시각' if row.get('source_type') == 'hackernews' else '발행')
            meta.append(e(note) + ' ' + e(_published(row['published_at'])))
        bullets = ''.join('<li>' + e(x) + '</li>' for x in row.get('bullets', []))
        reason = ('<p class="horizon-reason" style="color:' + dim + '"><strong>왜 볼 만한가</strong> · ' + e(row['reason']) + '</p>') if row.get('reason') else ''
        body.append('<article data-horizon-item="' + e(row.get('id', ''), quote=True) + '"><h3><a href="' + e(url, quote=True) + '" target="_blank" rel="noopener noreferrer" aria-label="' + e(row['title'] + ' — 원문, 새 창', quote=True) + '">' + e(row['title']) + '</a></h3><div class="horizon-meta" style="color:' + dim + '">' + ' · '.join(meta) + '</div><ul style="color:' + dim + '">' + bullets + '</ul>' + reason + '</article>')
    if status in ('complete', 'partial') and not body:message = '이번 기준을 통과한 자료가 없습니다.'
    else:message = messages.get(status, '')
    if status == 'partial':message = '일부 출처를 확인하지 못해, 확보된 자료로 구성했습니다.'
    notice = '<p role="status" style="font-size:12px;line-height:1.8;color:' + muted + ';margin:12px 0">' + e(message) + '</p>' if message else ''
    sources = []
    labels = {'rss': 'RSS', 'github': 'GitHub', 'hackernews': 'Hacker News'}
    for row in data.get('sources') or []:
        source_status = row.get('status', '')
        suffix = ' · 수집 확인 안 됨' if source_status in ('failed', 'error', 'unavailable') else ''
        if row.get('candidate_count') is not None:suffix += ' · ' + str(row['candidate_count']) + '건'
        sources.append('<li><a href="' + e(row['url'], quote=True) + '" target="_blank" rel="noopener noreferrer">' + e(row['name']) + '</a> · ' + e(labels.get(row.get('type'), row.get('type', ''))) + e(suffix) + '</li>')
    source_html = '<details class="horizon-sources" style="color:' + muted + '"><summary>살펴본 출처 ' + str(len(sources)) + '곳 보기</summary><ul style="padding-left:17px;margin:6px 0">' + ''.join(sources) + '</ul></details>' if sources else ''
    metrics = data.get('metrics') or {}
    coverage = (('최근 ' + str(metrics['lookback_hours']) + '시간의 ') if metrics.get('lookback_hours') else '')
    coverage += ('후보 ' + str(metrics['candidate_count']) + '건을 살펴봤습니다. ') if metrics.get('candidate_count') is not None else ''
    intro = e(coverage) + '관심 주제와 실무 활용을 기준으로 골랐습니다.' if body else ('확인한 공개자료를 선별 기준에 대조했습니다.' if status in ('complete', 'partial') else '여러 공개 출처에서 관심 주제와 실무 활용에 맞는 자료를 살펴보는 시범 브리핑입니다.')
    count = str(len(body)) + '건' if status in ('complete', 'partial') else '준비 상태'
    return ('<section id="horizon-briefing" class="horizon-briefing" data-horizon-date="' + e(date, quote=True) + '" data-horizon-status="' + e(status, quote=True) + '" style="--horizon-line:' + line + ';color:' + ink + '">'
        '<div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid ' + ink + '"><h2 style="font-size:12px;font-weight:800;letter-spacing:.04em;color:' + tone + '">Horizon 브리핑</h2><span style="font-size:11px;color:' + muted + '">' + count + '</span><span style="font-size:11px;color:' + muted + ';margin-left:auto">' + e(date) + ' · ' + pilot_label + '</span></div>'
        '<p style="font-size:11.5px;line-height:1.8;color:' + muted + ';margin:10px 0 0">' + intro + '</p>' + notice + '<div class="horizon-items">' + ''.join(body) + '</div>' + source_html +
        '<p style="font-size:10.5px;color:' + muted + ';line-height:1.8;margin:10px 0 0">처리 도구 · <a href="https://github.com/Thysrael/Horizon" target="_blank" rel="noopener noreferrer">Horizon</a> · 원문에 근거한 요약이며 선정 이유는 AI의 판단입니다.</p></section>')

def render_map(editions, tokens, pilot=None):
    return {date: render_section(edition, date, tokens, pilot) for date, edition in editions.items()}
