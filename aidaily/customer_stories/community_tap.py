"""Opt-in, single-room private tap. Never installs or activates a scheduler."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time
from urllib.parse import urlparse
from aidaily import config

SOURCE_ID = 'pro-vibelabs'
LABEL = '오픈채팅 · 모임 7'
LIMIT = 20000


def configuration_path():
    return Path(os.environ.get('CUSTOMER_STORIES_COMMUNITY_CONFIG', str(config.DATA_ROOT / 'customer_stories/community-sources.json'))).expanduser()


def approved_sources():
    path = configuration_path()
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding='utf-8'))
    sources = value.get('sources', [])
    enabled = [s for s in sources if s.get('enabled') is True and s.get('approved') is True]
    if len(enabled) > 1:
        raise ValueError('Only one approved community source is allowed')
    for source in enabled:
        if (source.get('id') != SOURCE_ID or source.get('anonymous_label') != LABEL
                or not re.fullmatch(r'[0-9]+', str(source.get('chat_id', '')))
                or source.get('ssh_user') != 'fovea'):
            raise ValueError('Community source scope is invalid')
    return enabled


def tap_path(source):
    return config.DATA_ROOT / 'customer_stories/community' / (source['id'] + '.jsonl')


def approved_tap_paths():
    return [(tap_path(s), s) for s in approved_sources()]


def timestamp(value):
    if isinstance(value, bool):
        raise ValueError('Invalid timestamp')
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp() if re.search(r'(Z|[+-]\d\d:\d\d)$', str(value)) else float('nan')
    if not math.isfinite(result) or result <= 0:
        raise ValueError('Invalid timestamp')
    return result


# Executed on pro: raw CLI output and stderr never leave that host.
REMOTE = r'''
import json, subprocess, sys
cid, since = sys.argv[1:3]
p = subprocess.run(['/Users/fovea/.openclaw/bin/kakaocli','messages','--chat-id',cid,'--since',since,'--limit','20000','--json'],capture_output=True,text=True)
if p.returncode: sys.exit(21)
try:
 data=json.loads(p.stdout)
 rows=data if isinstance(data,list) else data.get('messages',data.get('data',[]))
 if not isinstance(rows,list): raise ValueError()
 clean=[]
 for row in rows:
  if not isinstance(row,dict): continue
  room=row.get('chat_id',row.get('chatId',row.get('chatID')))
  if room is not None and str(room)!=cid: raise ValueError()
  def pick(*keys):
   return next((row[k] for k in keys if row.get(k) is not None),None)
  mid=pick('id','logId','log_id')
  text=pick('text','message','content','plainText','body')
  stamp=pick('timestamp','ts','sentAt','sent_at')
  kind=pick('type')
  if not isinstance(mid,(str,int)) or isinstance(mid,bool) or not isinstance(text,str) or not isinstance(stamp,(str,int,float)) or isinstance(stamp,bool): continue
  if not isinstance(kind,(str,int,float,bool,type(None))): kind=None
  clean.append(dict(id=mid,text=text,type=kind,timestamp=stamp))
 print(json.dumps({'messages':clean,'received_count':len(rows)},ensure_ascii=False))
except Exception: sys.exit(22)
'''


def fetch(source, since, runner=subprocess.run):
    if not re.fullmatch(r'[1-9][0-9]*(?:h|d)', since):
        raise ValueError('Invalid since interval')
    registry_path = Path(os.environ.get('ABOT_SERVICES_FILE', '~/Library/Application Support/abot/services.json')).expanduser()
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    endpoint = registry.get('services', registry)['abot-host-web']['instances']['pro']['tailnet']
    host = urlparse(endpoint if '://' in endpoint else 'https://' + endpoint).hostname
    if not host or not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('Invalid registered host')
    remote = 'python3 -c ' + shlex.quote(REMOTE) + ' ' + shlex.quote(str(source['chat_id'])) + ' ' + shlex.quote(since)
    result = runner(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=pro',source['ssh_user']+'@'+host,remote],capture_output=True,text=True,timeout=180)
    if result.returncode:
        raise RuntimeError('Selected community fetch failed (status %s)' % result.returncode)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or not isinstance(payload.get('messages'), list) or type(payload.get('received_count')) is not int:
        raise ValueError('Invalid selected community response')
    return payload


def normalize(source, payload):
    rows, invalid = [], 0
    for row in payload['messages']:
        try:
            mid = str(row['id'])
            if not re.fullmatch(r'[0-9]+', mid) or not isinstance(row['text'], str):
                raise ValueError()
            rows.append(dict(id=mid,chat_id=str(source['chat_id']),chat_name=LABEL,text=row['text'],type=row.get('type'),ts=timestamp(row['timestamp'])))
        except (KeyError, ValueError, TypeError, OverflowError):
            invalid += 1
    return rows, invalid


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def collect(since='24h', output=None, fetch_only=False, fetcher=fetch, clock=time.time):
    sources = approved_sources()
    if not sources:
        return {'status':'disabled'}
    if fetch_only and (not output or not Path(output).is_absolute()):
        raise ValueError('Fetch-only requires an absolute private output path')
    match = re.fullmatch(r'([1-9][0-9]*)(h|d)', since)
    if not match:
        raise ValueError('Invalid since interval')
    requested_end = timestamp(clock())
    requested_start = requested_end - int(match.group(1)) * (3600 if match.group(2) == 'h' else 86400)
    source = sources[0]
    payload = fetcher(source,since)
    normalized, invalid = normalize(source,payload)
    acquired_times = [r['ts'] for r in normalized]
    rows = [r for r in normalized if requested_start <= r['ts'] < requested_end]
    times = [r['ts'] for r in rows]
    receipt = dict(status='fetched',source_id=SOURCE_ID,requested_since=since,
                   requested_start=requested_start,requested_end=requested_end,
                   window_semantics='start_inclusive_end_exclusive_utc_epoch_seconds',
                   received_count=payload['received_count'],accepted_count=len(rows),
                   invalid_count=payload['received_count']-len(normalized),
                   outside_window_count=len(normalized)-len(rows),limit=LIMIT,
                   limit_reached=payload['received_count']>=LIMIT,
                   acquired_oldest_ts=min(acquired_times) if acquired_times else None,
                   acquired_newest_ts=max(acquired_times) if acquired_times else None,
                   oldest_ts=min(times) if times else None,newest_ts=max(times) if times else None,
                   history_completeness='not_verified',fetched_at=dt.datetime.now(dt.timezone.utc).isoformat())
    if fetch_only:
        atomic_write(output,json.dumps(dict(receipt=receipt,messages=rows),ensure_ascii=False)+'\n')
        return receipt
    path = tap_path(source)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock_fd = os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(lock_fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []
        merged = {(str(r['chat_id']),str(r['id'])):r for r in previous}
        merged.update({(r['chat_id'],r['id']):r for r in rows})
        atomic_write(path,''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(merged.values(),key=lambda r:(r['ts'],r['id']))))
        atomic_write(path.with_suffix('.receipt.json'),json.dumps(receipt,ensure_ascii=False)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--since',default='24h')
    parser.add_argument('--fetch-only',action='store_true')
    parser.add_argument('--output')
    args=parser.parse_args()
    print(json.dumps(collect(args.since,args.output,args.fetch_only),ensure_ascii=False))

if __name__ == '__main__':
    main()
