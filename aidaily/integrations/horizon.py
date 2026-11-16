"""Bounded public source collection for the Horizon pilot.

Only configured public RSS, Hacker News and GitHub feeds are requested. Network
access is through the project's shared HTTP integration; no private credentials.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import hashlib
import html
import json
import re
import sys
from urllib.parse import unquote, urlsplit
from aidaily import config
from aidaily.integrations import http


def _plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def _url(value):
    try:
        p=urlsplit(value)
        return bool(p.scheme=='https' and p.hostname and not p.username and not p.password and not any(ord(c)<33 for c in value))
    except (TypeError, ValueError):return False


def collect(source, *, limit=8, now=None, lookback_hours=72, fetch=http.request_bytes):
    """Return explicit source status and bounded entries; failures are not zero data."""
    now=now or dt.datetime.now(dt.timezone.utc)
    result={'id':source['id'],'name':source['name'],'type':source['type'],'url':source['url'],'status':'ok','candidate_count':0,'lookback_hours':lookback_hours,'collected_at':now.isoformat(),'newest_published_at':None}
    if source['type'] not in ('rss','github','hackernews') or not _url(source['url']):
        raise ValueError('unsupported source configuration')
    try:
        raw,_=fetch(source['url'],headers={'User-Agent':'AI-Daily-Horizon-Pilot/1.0'},timeout=15)
        candidates=[]
        if source['type']=='hackernews':
            for row in json.loads(raw).get('hits',[]):
                link=row.get('url') or ('https://news.ycombinator.com/item?id='+str(row.get('objectID','')))
                candidates.append((row.get('title'),link,row.get('created_at'),row.get('story_text') or row.get('title')))
        else:
            import feedparser
            feed=feedparser.parse(raw)
            if feed.bozo and not feed.entries:raise ValueError('invalid feed')
            for row in feed.entries:
                when=row.get('published') or row.get('updated') or ''
                candidates.append((row.get('title'),row.get('link'),when,row.get('summary') or row.get('title')))
        out=[]
        for title,link,when,body in candidates:
            title=_plain(title);body=_plain(body)
            if not title or not _url(link):continue
            # GitHub feed titles can omit the prerelease tag suffix; the tag
            # in the canonical release URL is the exact version identifier.
            if source['type']=='github':
                path=urlsplit(link).path
                match=re.search(r'/releases/tag/([^/]+)$',path)
                if match:
                    tag=unquote(match.group(1))
                    if re.fullmatch(r'v?\d[0-9A-Za-z._+-]*',tag):title=tag
            try:
                from email.utils import parsedate_to_datetime
                try: timestamp=dt.datetime.fromisoformat(str(when).replace('Z','+00:00'))
                except ValueError: timestamp=parsedate_to_datetime(str(when))
                if timestamp.tzinfo is None:timestamp=timestamp.replace(tzinfo=dt.timezone.utc)
                timestamp=timestamp.astimezone(dt.timezone.utc)
            except (ValueError,TypeError,OverflowError):continue
            if timestamp>now+dt.timedelta(minutes=10) or timestamp<now-dt.timedelta(hours=lookback_hours):continue
            key=hashlib.sha256(link.encode()).hexdigest()[:24]
            out.append({'id':source['id']+':'+key,'title':title,'url':link,'source_name':source['name'],
                        'source_type':source['type'],'published_at':timestamp.isoformat(),'content':body[:6000]})
            if len(out)>=limit:break
        result['candidate_count']=len(out)
        result['newest_published_at']=max((x['published_at'] for x in out),default=None)
        return result,out
    except Exception as error:
        result.update(status='unavailable',error_type=type(error).__name__)
        return result,[]


async def _safe_original_request(url):
    import httpx
    upstream=str(config.DATA_ROOT/'ai_news/horizon/upstream')
    if upstream not in sys.path:sys.path.insert(0,upstream)
    from src.url_security import safe_request
    async with httpx.AsyncClient(timeout=20,trust_env=False) as client:
        response=await safe_request(client,'GET',url,headers={'User-Agent':'AI-Daily-Horizon-Pilot/1.0'})
        response.raise_for_status()
        return response.content


def fetch_original(url, *, fetch=None):
    """Return substantial readable public source text; never infer it from a title."""
    if not _url(url):
        raise ValueError('invalid public article URL')
    if fetch is None:
        raw=asyncio.run(_safe_original_request(url))
    else:
        # Explicit injected fetch is reserved for offline tests.
        raw,_=fetch(url, headers={'User-Agent':'AI-Daily-Horizon-Pilot/1.0'}, timeout=20)
    if len(raw)>8_000_000:
        raise ValueError('article too large')
    document=raw.decode('utf-8','replace')
    import trafilatura
    from aidaily.integrations.article_reader import extract_article_text
    text=(trafilatura.extract(document,include_comments=False,include_tables=False) or extract_article_text(document)).strip()
    return text[:12000] if len(text)>=250 else ''
