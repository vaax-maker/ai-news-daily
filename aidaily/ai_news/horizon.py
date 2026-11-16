"""Horizon pilot: pinned upstream ranking, deduplication and enrichment.

This command creates a local edition only. It never publishes or sends messages.
Use the project-local Horizon virtualenv; upstream source remains unmodified.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import datetime as dt
from difflib import SequenceMatcher
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from aidaily import config
from aidaily.integrations import horizon as source_api
from aidaily.integrations import openrouter

ROOT=config.DATA_ROOT/'ai_news/horizon'
REVISION='cdd95f8e881673057e3e201717836da4b8e2e0e7'
REPOSITORY='https://github.com/Thysrael/Horizon'


def _save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.new')
    with temp.open('w',encoding='utf-8') as f:
        os.chmod(temp,0o600);json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def _load_engine():
    source=ROOT/'upstream'
    head=subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    if head!=REVISION:raise RuntimeError('Horizon upstream revision mismatch')
    sys.path.insert(0,str(source))
    from src.ai.client import AIClient
    from src.ai.analyzer import ContentAnalyzer
    from src.ai.enricher import ContentEnricher
    from src.ai.errors import AIProviderUnavailableError
    from src.models import ContentItem, SourceType
    from src.processing.profiles import ProfileRegistry
    from src.orchestrator import HorizonOrchestrator as Orchestrator, _deduplication_url_key

    class FleetClient(AIClient):
        async def complete(self, system, user, temperature=None, max_tokens=None):
            try:
                # The shared client journals a content-derived request ID. Never
                # turn a busy/unknown job into a fresh paid submission.
                return await asyncio.to_thread(openrouter.complete,system,user,
                    temperature=0.2 if temperature is None else temperature,
                    max_tokens=max_tokens,allow_external=False)
            except Exception as exc:
                # Horizon's batch helpers otherwise catch and replace failures
                # with empty scores; this exception stops their retry machinery.
                raise AIProviderUnavailableError(type(exc).__name__) from exc
    registry=ProfileRegistry.load(ROOT/'profiles','tech-news')
    client=FleetClient()
    return ContentAnalyzer(client,registry,concurrency=1), ContentEnricher(client,registry,['ko'],concurrency=1), ContentItem,SourceType,Orchestrator,_deduplication_url_key


def _engine_contract(root):
    """Freeze profile and upstream prompt-processing code used for requests."""
    paths = sorted((root / 'profiles' / 'tech-news').glob('*'))
    paths += [root / 'upstream' / 'src' / 'ai' / name for name in ('analyzer.py','enricher.py','prompting.py') if (root / 'upstream' / 'src' / 'ai' / name).is_file()]
    paths += sorted((root / 'upstream' / 'src' / 'ai' / 'prompting').rglob('*.py'))
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


def _existing(date=None):
    try:
        index=json.loads((config.DOCS_ROOT/'search-index.json').read_text())
        rows=[row for row in index if isinstance(row,dict)] if isinstance(index,list) else []
    except (OSError,ValueError):
        rows=[]
    try:
        history=json.loads((ROOT/'published-history.json').read_text())
        if isinstance(history,list):
            for edition in history:
                if not isinstance(edition,dict) or edition.get('status')!='published':continue
                prior=edition.get('date')
                if not isinstance(prior,str):continue
                try:previous=dt.date.fromisoformat(prior)
                except ValueError:continue
                if date and previous>=dt.date.fromisoformat(date):continue
                items=edition.get('items')
                if isinstance(items,list):rows.extend(item for item in items if isinstance(item,dict))
    except (OSError,ValueError):
        pass
    return rows


def _title_key(value):return re.sub(r'[^a-z0-9가-힣]','',str(value).casefold())


def _overlap(item, existing, url_key):
    key=url_key(item['url']);title=_title_key(item['title'])
    for row in existing:
        url=row.get('url') or ''
        try:
            if url and url_key(url)==key:return True
        except (TypeError,ValueError):pass
        other=_title_key(row.get('title',''))
        if len(title)>=18 and len(other)>=18 and SequenceMatcher(None,title,other).ratio()>=.92:return True
    return False


def _select(rows, limit, minimum):
    ranked=sorted((x for x in rows if x.get('score') is not None and x['score']>=minimum),key=lambda x:(-x['score'],x['id']))
    selected=[];counts={}
    for item in ranked:
        source=item['source_name']
        if counts.get(source,0)>=2:continue
        selected.append(item);counts[source]=counts.get(source,0)+1
        if len(selected)>=limit:break
    return selected


def _item_attribution(row, title):
    """Keep source timestamps and release identifiers faithful to their origin."""
    parsed=urlsplit(row['url'])
    host=(parsed.hostname or '').removeprefix('www.')
    info={'publisher_hostname':host}
    if row['source_type']=='hackernews':
        info['published_at_note']='Hacker News 게시 시각'
    if row['source_type']=='github':
        match=re.search(r'/releases/tag/([^/]+)$',parsed.path)
        if match:
            tag=unquote(match.group(1))
            if re.fullmatch(r'v?\d[0-9A-Za-z._+-]*',tag):
                info['release_tag']=tag
                if tag.casefold() not in title.casefold():title=f'{tag} — {title}'
    return title,info


def _sentences(text):
    lines=[re.sub(r'^[-*•]\s*','',x).strip() for x in re.split(r'\n+|(?<=[.!?])\s+',str(text)) if x.strip()]
    return lines[:3]


def run(date, *, root=ROOT):
    root=Path(root);settings=json.loads((root/'settings.json').read_text());pilot=settings['pilot']
    day=dt.date.fromisoformat(date)
    if not dt.date.fromisoformat(pilot['start'])<=day<=dt.date.fromisoformat(pilot['end']):raise ValueError('outside seven-day pilot window')
    if root.resolve()!=ROOT.resolve():raise ValueError('runtime root override not supported')
    analyzer,enricher,Item,SourceType,Orchestrator,url_key=_load_engine()
    runs=root/'runs';runs.mkdir(parents=True,exist_ok=True)
    with (runs/(date+'.lock')).open('a') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        path=runs/(date+'.json')
        state=json.loads(path.read_text()) if path.exists() else None
        if state and state.get('status')=='collection_unavailable':
            # A source failure is retryable only before any candidate or AI work.
            # Preserve each failed receipt under this date's lock before retrying.
            if (any(state.get(key) for key in ('candidates','analyzed','enriched','originals'))
                    or 'pending' in state or 'current' in state):
                raise RuntimeError('collection failure has work attached; review required')
            sequence=1
            while (runs/f'{date}.collection-failure-{sequence:04d}.json').exists():
                sequence+=1
            _save(runs/f'{date}.collection-failure-{sequence:04d}.json',state)
            state=None
        if state is None:
            receipts=[];raw=[]
            lookback_hours=72 if date==pilot['start'] else 24
            for source in settings['sources']:
                receipt,items=source_api.collect(source,limit=settings['per_source_limit'],lookback_hours=lookback_hours)
                receipts.append(receipt);raw.extend(items)
            if not any(r['status']=='ok' for r in receipts):
                _save(path,{'date':date,'status':'collection_unavailable','sources':receipts})
                raise RuntimeError('all configured public sources unavailable')
            # Horizon's real cross-source merge operates on ContentItem objects.
            inputs=[Item(id=x['id'],source_type=SourceType(x['source_type']),title=x['title'],url=x['url'],
                         content=x['content'],published_at=x['published_at'],profile='tech-news',
                         metadata={'source_name':x['source_name']}) for x in raw]
            merged=Orchestrator.merge_cross_source_duplicates(None,inputs)
            existing=_existing(date);candidates=[];overlaps=[]
            for item in merged:
                row={'id':item.id,'title':item.title,'url':str(item.url),'source_name':item.metadata['source_name'],
                     'source_type':item.source_type.value,'published_at':item.published_at.isoformat(),
                     'content':item.content or '', 'related_sources':item.metadata.get('merged_sources',[])}
                (overlaps if _overlap(row,existing,url_key) else candidates).append(row)
            candidates=candidates[:settings['candidate_limit']]
            state={'date':date,'status':'scoring','pilot':pilot,'settings':settings,'sources':receipts,
                   'candidates':candidates,'overlap_count':len(overlaps),'analyzed':{},'enriched':{},'originals':{},'engine_contract':_engine_contract(root)}
            _save(path,state)
        if state.get('status') in ('collection_unavailable','review_required'):raise RuntimeError('run requires review; preserve receipt')
        if state.get('status')=='complete':
            edition_path=root/'editions'/(date+'.json')
            if not edition_path.exists():raise RuntimeError('completed run missing edition')
            return json.loads(edition_path.read_text())
        if state.get('engine_contract') != _engine_contract(root):
            raise RuntimeError('frozen engine/profile contract missing or changed; review required')
        opts=state['settings'];candidates=state['candidates']
        async def process():
            for row in candidates:
                if row['id'] in state['analyzed']:continue
                obj=Item(id=row['id'],source_type=SourceType(row['source_type']),title=row['title'],url=row['url'],
                         content=row['content'],published_at=row['published_at'],profile='tech-news')
                state.update(status='scoring',current={'item_id':row['id'],'phase':'score'});_save(path,state)
                try:
                    # Execute original per-item implementation, bypassing its
                    # broad retry decorator to keep uncertain work resumable.
                    await analyzer._analyze_item.__wrapped__(analyzer,obj)
                except Exception as exc:
                    state.update(status='pending' if isinstance(exc.__cause__ or exc,openrouter.CompletionPending) else 'review_required',pending={'item_id':row['id'],'phase':'score','error_type':type(exc.__cause__ or exc).__name__, 'request_id':getattr(exc.__cause__ or exc,'request_id',None)});_save(path,state);raise
                analysis=obj.processing.analysis if obj.processing else None
                if not analysis or analysis.score is None:
                    state.update(status='review_required',pending={'item_id':row['id'],'phase':'score','error_type':'invalid_output'});_save(path,state);raise RuntimeError('Horizon score invalid')
                state['analyzed'][row['id']]=analysis.model_dump();state['status']='scoring';state.pop('pending',None);state.pop('current',None);_save(path,state)
            ranked=[{**x,**state['analyzed'][x['id']]} for x in candidates]
            ordered=_select(ranked,len(ranked),opts['minimum_score'])
            selected=[];source_counts={};originals=state.setdefault('originals',{})
            for row in ordered:
                if len(selected)>=opts['selected_limit']:break
                if source_counts.get(row['source_name'],0)>=2:continue
                if row['id'] not in originals:
                    state.update(status='fetching_original',current={'item_id':row['id'],'phase':'original'});_save(path,state)
                    try:
                        body=await asyncio.to_thread(source_api.fetch_original,row['url'])
                        error=None
                    except Exception as exc:
                        body='';error=type(exc).__name__
                    originals[row['id']]={'status':'ok' if body else 'no_original_body','url':row['url'],
                        'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat(),'text':body,
                        'sha256':hashlib.sha256(body.encode()).hexdigest() if body else None,'error_type':error}
                    _save(path,state)
                original=originals[row['id']]
                if original['status']!='ok':continue
                selected.append(row);source_counts[row['source_name']]=source_counts.get(row['source_name'],0)+1
                if row['id'] in state['enriched']:continue
                obj=Item(id=row['id'],source_type=SourceType(row['source_type']),title=row['title'],url=row['url'],
                         content=original['text'],published_at=row['published_at'],profile='tech-news')
                await analyzer.classifier.resolve(obj)
                from src.models import ContentAnalysis
                obj.processing.analysis=ContentAnalysis.model_validate(state['analyzed'][row['id']])
                state.update(status='enriching',current={'item_id':row['id'],'phase':'enrich'});_save(path,state)
                try:await enricher._enrich_item(obj)
                except Exception as exc:
                    state.update(status='pending' if isinstance(exc.__cause__ or exc,openrouter.CompletionPending) else 'review_required',pending={'item_id':row['id'],'phase':'enrich','error_type':type(exc.__cause__ or exc).__name__, 'request_id':getattr(exc.__cause__ or exc,'request_id',None)});_save(path,state);raise
                artifact=obj.processing.artifacts.get('ko')
                if not artifact or not artifact.blocks:
                    state.update(status='review_required',pending={'item_id':row['id'],'phase':'enrich','error_type':'empty_output'});_save(path,state)
                    raise RuntimeError('Horizon enrichment empty')
                state['enriched'][row['id']]={'title':artifact.title,'bullets':_sentences(artifact.blocks[0].content)};_save(path,state)
            return selected
        selected=asyncio.run(process())
        items=[]
        for x in selected:
            enrichment=state['enriched'][x['id']]
            if not enrichment['bullets']:raise RuntimeError('Horizon enrichment empty')
            title,attribution=_item_attribution(x,enrichment['title'])
            items.append({k:x[k] for k in ('id','url','source_name','source_type','published_at','score','reason','related_sources')} | {'title':title,'bullets':enrichment['bullets']} | attribution)
        edition={'status':'complete','date':date,'pilot':pilot,'engine':{'name':'Horizon','repository':REPOSITORY,'revision':REVISION},'sources':state['sources'],'items':items,'metrics':{'candidate_count':len(candidates),'selected_count':len(items),'new_count':len(items),'overlap_count':state['overlap_count'],'source_count':sum(x['status']=='ok' for x in state['sources']),'overlap_method':'canonical_url_or_normalized_title_similarity_0.92','original_body_excluded_count':sum(x['status']!='ok' for x in state.get('originals',{}).values()),'lookback_hours':72 if date==pilot['start'] else 24}}
        _save(root/'editions'/(date+'.json'),edition);state.update(status='complete');state.pop('pending',None);state.pop('current',None);_save(path,state)
        return edition


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--date',default=dt.date.today().isoformat());args=parser.parse_args()
    result=run(args.date);print(json.dumps({'date':result['date'],'status':result['status'],'metrics':result['metrics']},ensure_ascii=False))

if __name__=='__main__':main()
