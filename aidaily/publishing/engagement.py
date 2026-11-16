"""Stable article identity and anonymous public-page instrumentation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote


def stable_uid(row):
    if re.fullmatch(r'[a-f0-9]{64}', str(row.get('uid', ''))):
        return row['uid']
    raw = str(row.get('url') or '')
    try:
        u = urlsplit(raw)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
            raise ValueError()
        host = u.hostname.lower()
        if u.port and not ((u.scheme == 'https' and u.port == 443) or (u.scheme == 'http' and u.port == 80)):
            host += ':' + str(u.port)
        pairs = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                 if not re.match(r'^(utm_|fbclid|gclid|cache)', k, re.I)]
        pairs.sort(key=lambda pair: pair[0])
        normalized = urlunsplit((u.scheme, host, quote(u.path or '/', safe="/%:@!$&'()*+,;=-._~"), urlencode(pairs), ''))
    except (ValueError, TypeError):
        normalized = ''
    kind = row.get('kind', '')
    generic = not normalized or re.search(r'(?:archive|index|daily)\.html(?:\?|$)', normalized, re.I)
    if kind == 'customer_story':
        index = next((row.get(k) for k in ('publication_index', 'customer_story_index', 'id') if row.get(k) is not None), None)
        seed = f"{row.get('date')}:{index}"
    elif kind == 'ai_news' and generic:
        title = ' '.join(unicodedata.normalize('NFKC', str(row.get('title') or '')).split())
        seed = f"{row.get('date')}:{title}"
    else:
        seed = normalized
    return hashlib.sha256(f'{kind}:{seed}'.encode()).hexdigest()


def collector_url():
    registry = Path(os.environ.get('ABOT_SERVICES_FILE', '~/Library/Application Support/abot/services.json')).expanduser()
    try:
        url = json.loads(registry.read_text())['services']['aidaily-engagement']['endpoints']['public_event']
        if not str(url).startswith('https://'):
            return ''
        return url
    except (OSError, ValueError, KeyError, TypeError):
        return ''


def instrument_html(page, endpoint=None):
    endpoint = collector_url() if endpoint is None else endpoint
    if not endpoint or not re.search(r'<(?:html|meta|head|body|title)\b', page, re.I) or re.search(r'<meta[^>]+http-equiv=["\']?refresh', page, re.I):
        return page
    page = re.sub(r'<script\b[^>]*id="aidaily-pv"[^>]*>.*?</script>', '', page, flags=re.S)
    script = r'''<script id="aidaily-pv">(()=>{
if(!['wootom.github.io','vaax-maker.github.io'].includes(location.hostname))return;
const endpoint=ENDPOINT;let last='';const pending=new Set();
function view(){try{
 if(document.visibilityState==='hidden'||document.prerendering)return;
 const u=new URL(location.href);let date=u.searchParams.get('date')||'';
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date)){const m=u.pathname.match(/(\d{4}-\d{2}-\d{2})/);const label=(document.getElementById('dailyDateLabel')?.textContent||'').match(/\d{4}\.\d{2}\.\d{2}/);date=m?m[1]:label?label[0].replaceAll('.','-'):'';}
 const page=u.origin+u.pathname;const key=page+'|'+date;if(key===last)return;last=key;
 const id=globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'_'+Math.random().toString(36).slice(2);
 const q=new URL(endpoint);q.searchParams.set('event_id',id);q.searchParams.set('page',page);if(date)q.searchParams.set('date',date);
 const frame=document.createElement('iframe');frame.hidden=true;frame.setAttribute('aria-hidden','true');frame.title='';frame.setAttribute('sandbox','allow-same-origin');frame.setAttribute('allow',"local-network-access 'none'; local-network 'none'; loopback-network 'none'");
 frame.srcdoc='<img crossorigin="anonymous" referrerpolicy="origin" src="'+q.href.replaceAll('&','&amp;').replaceAll('"','&quot;')+'">';pending.add(frame);const cleanup=()=>{frame.remove();pending.delete(frame);};frame.onload=()=>setTimeout(cleanup,1000);setTimeout(cleanup,30000);document.body.append(frame);
}catch{}}
for(const method of ['pushState','replaceState']){const original=history[method];history[method]=function(...args){const result=original.apply(this,args);queueMicrotask(view);return result;};}
addEventListener('popstate',view);document.addEventListener('visibilitychange',view);view();
})();</script>'''.replace('ENDPOINT', json.dumps(endpoint).replace('<', '\\u003c'))
    if re.search(r'</body>', page, re.I):
        return re.sub(r'</body>', lambda match: script + match[0], page, count=1, flags=re.I)
    return page + '\n' + script


def instrument_directory(root, paths=None):
    root = Path(root)
    changed = []
    for path in (map(Path, paths) if paths is not None else root.glob('*.html')):
        if not path.is_absolute():
            path = root / path
        before = path.read_text(encoding='utf-8')
        after = instrument_html(before)
        if after != before:
            path.write_text(after, encoding='utf-8')
            changed.append(str(path))
    return changed
