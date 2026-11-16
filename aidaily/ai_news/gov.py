"""Generate a private, resumable government-announcement edition; no publication."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit,parse_qsl,urlencode
import uuid
from aidaily import config
from aidaily.integrations import gov as remote

ROOT=config.DATA_ROOT/'ai_news/gov'
BASE='https://www.bizinfo.go.kr/'
INCLUDE=('인공지능','머신러닝','딥러닝','ai','xr','vr','ar','메타버스','가상현실','증강현실','디지털트윈','실감콘텐츠','영상콘텐츠','뉴미디어','미디어 플랫폼','데이터센터','클라우드','고성능 컴퓨팅','기술개발','연구개발','r&d','실증사업','플랫폼 개발','시스템 개발','솔루션 개발','스마트시티','iot','양자','gpu')
EXCLUDE=('유지관리','유지보수','청소','경비','시설관리','장비 구매','물품 구매','납품','홍보물','현수막','자판기')
KST=dt.timezone(dt.timedelta(hours=9))

def _save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix(path.suffix+'.new')
    with temp.open('w',encoding='utf-8') as f:
        os.chmod(temp,0o600);json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def _plain(value,limit):
    if not isinstance(value,str):return ''
    text=html.unescape(re.sub(r'<[^>]*>',' ',value));return re.sub(r'\s+',' ',text).strip()[:limit]

def _normal(row):
    if not isinstance(row,dict):return None
    title=_plain(row.get('pblancNm') or row.get('title'),250)
    link=row.get('pblancUrl') or row.get('link')
    if not title or not isinstance(link,str) or not link.strip():return None
    try:
        p=urlsplit(link.strip());pairs=parse_qsl(p.query,keep_blank_values=True,strict_parsing=True)
    except ValueError:return None
    if (p.scheme!='https' or p.netloc!='www.bizinfo.go.kr' or p.path!='/sii/siia/selectSIIA200Detail.do'
            or p.fragment or len(pairs)!=1 or pairs[0][0]!='pblancId'):return None
    url_id=pairs[0][1];field_id=_plain(row.get('pblancId'),80)
    if field_id and field_id!=url_id:return None
    raw_id=field_id or url_id
    if not re.fullmatch(r'PBLN_[A-Za-z0-9_-]{1,70}',raw_id):return None
    link='https://www.bizinfo.go.kr'+p.path+'?'+urlencode({'pblancId':raw_id})
    return {'id':raw_id,'title':title,'url':link,'source_name':'기업마당','agency':_plain(row.get('jrsdInsttNm') or row.get('author') or row.get('excInsttNm'),150),'published_date':_plain(row.get('creatPnttm') or row.get('pubDate'),30)[:10], 'published_at':_plain(row.get('creatPnttm') or row.get('pubDate'),30), 'application_period':_plain(row.get('reqstBeginEndDe') or row.get('reqstDt'),120), 'summary':_plain(row.get('bsnsSumryCn') or row.get('description'),650)}

def _relevant(item):
    title=item['title'];text=(title+' '+item['summary']).casefold()
    if any(term.casefold() in title.casefold() for term in EXCLUDE):return False
    for term in INCLUDE:
        if term in ('ai','xr','vr','ar','iot','gpu'):
            if re.search(r'(?<![a-z])'+term+r'(?![a-z])',text):return True
        elif term.casefold() in text:return True
    return False

def _topic_weight(item):
    title=item.get('title','');text=(title+' '+item.get('summary','')).casefold()
    if '취소' in title:return -1
    if re.search(r'(?<![a-z])(?:ai|ml|dl|xr|vr|ar|gpu)(?![a-z])',text):return 2
    if any(word in text for word in ('인공지능','머신러닝','딥러닝','실감','클라우드','가상현실','증강현실','디지털트윈')):return 2
    return 0

def _rank(items):
    # Stable sorts: relevance first, most recent first for equal relevance.
    items.sort(key=lambda x:x.get('published_at') or x['published_date'],reverse=True)
    items.sort(key=_topic_weight,reverse=True)


def _hash(item):
    return hashlib.sha256(json.dumps({k:v for k,v in item.items() if k!='published_at'},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def _deadline(period):
    # Require an explicit end date after a range separator; no guessed deadline.
    m=re.search(r'(?:~|～|∼)\s*(\d{4})[-./]?(\d{2})[-./]?(\d{2})(?!\d)',period)
    if not m:return None
    try:return dt.date(*(int(v) for v in m.groups()))
    except ValueError:return None

def _prior(root,date):
    for p in sorted((root/'private').glob('????-??-??-bizinfo-local-00.json'),reverse=True):
        if p.name[:10]>=date:continue
        try:
            sample=json.loads(p.read_text());edition=json.loads((root/'editions'/(p.name[:10]+'.json')).read_text())
            if sample.get('status')=='ok' and any(x.get('id')=='bizinfo' and x.get('status')=='ok' for x in edition.get('sources',[])):
                items=[v for r in sample.get('records',[]) if (v:=_normal(r)) is not None]
                return {v['id']:_hash(v) for v in items}
        except (OSError,ValueError,TypeError):continue
    for p in sorted((root/'private').glob('????-??-??.json'),reverse=True):
        if p.stem>=date:continue
        try:
            s=json.loads(p.read_text());run=json.loads((root/'runs'/p.name).read_text())
            if run.get('status')=='complete' and isinstance(s.get('items'),list):return {i['id']:_hash(i) for i in s['items']}
        except (ValueError,OSError,KeyError,TypeError):continue
    return None

def _public_normal(source,row):
    if not isinstance(row,dict):return None
    if source=='msit':
        title=_plain(row.get('subject'),250);link=row.get('viewUrl');agency=_plain(row.get('deptName'),150);published_at=_plain(row.get('pressDt'),30);published=published_at[:10]
        required={'sCode','mId','mPid','bbsSeqNo','nttSeqNo'};host='www.msit.go.kr';path='/bbs/view.do'
    else:
        title=_plain(row.get('bidNtceNm'),250);link=row.get('bidNtceDtlUrl');agency=_plain(row.get('dminsttNm') or row.get('ntceInsttNm'),150);published_at=_plain(row.get('bidNtceDt'),30);published=published_at[:10]
        required={'bidPbancNo','bidPbancOrd'};host='www.g2b.go.kr';path='/link/PNPE027_01/single/'
    if not title or not isinstance(link,str):return None
    try:p=urlsplit(link);pairs=parse_qsl(p.query,keep_blank_values=True,strict_parsing=True)
    except ValueError:return None
    if p.scheme!='https' or p.netloc!=host or p.path!=path or p.fragment or len(pairs)!=len(required) or {k for k,v in pairs}!=required:return None
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v) for k,v in pairs):return None
    query=dict(pairs)
    if source=='msit' and (query['sCode']!='user' or any(not re.fullmatch(r'\d{1,24}',query[k]) for k in ('mId','mPid','bbsSeqNo','nttSeqNo'))):return None
    if source=='koneps' and not re.fullmatch(r'\d{1,10}',query['bidPbancOrd']):return None
    if source=='msit':identifier='msit:'+query['bbsSeqNo']+':'+query['nttSeqNo'];period=''
    else:
        if str(row.get('bidNtceNo',''))!=query['bidPbancNo'] or str(row.get('bidNtceOrd',''))!=query['bidPbancOrd']:return None
        identifier='koneps:'+query['bidPbancNo']+':'+query['bidPbancOrd']
        begin=_plain(row.get('bidBeginDt'),30);end=_plain(row.get('bidClseDt'),30);period=(begin+' ~ '+end) if begin and end else ''
    return {'id':identifier,'title':title,'url':'https://'+host+path+'?'+urlencode(pairs),'source_name':'과학기술정보통신부' if source=='msit' else '나라장터','agency':agency,'published_date':published,'published_at':published_at,'application_period':period,'summary':''}

def _prior_public(root,date,source):
    for p in sorted((root/'private').glob('????-??-??-'+source+'-*.json'),reverse=True):
        if p.name[:10]>=date:continue
        try:
            x=json.loads(p.read_text())
            edition=json.loads((root/'editions'/(p.name[:10]+'.json')).read_text())
            if x.get('status')=='ok' and any(r.get('id')==source and r.get('status')=='ok' for r in edition.get('sources',[])):
                # Compare against all successful keyword samples for that date.
                old={}
                for q in (root/'private').glob(p.name[:10]+'-'+source+'-*.json'):
                    y=json.loads(q.read_text())
                    if y.get('status')=='ok':
                        for r in y.get('records',[]):
                            item=_public_normal(source,r)
                            if item:old[item['id']]=_hash(item)
                return old
        except (OSError,ValueError,TypeError):continue
    return None

def _repair_checked_at(edition,path):
    """Use the newest valid per-source observation, preserving source values."""
    candidates=[]
    for source in edition.get('sources',[]):
        value=source.get('checked_at') if isinstance(source,dict) else None
        if not isinstance(value,str):continue
        try:
            parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is None:continue
            candidates.append((parsed.astimezone(dt.timezone.utc),value))
        except (ValueError,OverflowError):continue
    if candidates:
        latest=max(candidates,key=lambda x:x[0])[1]
        if edition.get('checked_at')!=latest:
            edition['checked_at']=latest;_save(path,edition)
    return edition


def _expand(date,root,state,out):
    # Preserve earlier editions; local Bizinfo collection has its own checkpoint.
    base=json.loads(out.read_text())
    if base.get('status')=='complete' and base.get('selection_revision')==3 and {x.get('id') for x in base.get('sources',[]) if x.get('status')=='ok' and x.get('origin')=='mini1_https'}=={'bizinfo','msit','koneps'}:return _repair_checked_at(base,out)
    backup=root/'editions'/(date+'.before-mini1-direct.json')
    if not backup.exists() and base.get('selection_revision')!=3:_save(backup,base)
    checked=base.get('checked_at') or dt.datetime.now(dt.timezone.utc).isoformat();all_items=[];metrics_by_source={};sources=[];baselines={}
    cp=root/'private'/f'{date}-bizinfo-local-00.json'
    if cp.exists():receipt=json.loads(cp.read_text())
    else:
        receipt={'date':date,'source':'bizinfo','attempt':1,'status':'fetching','reason_code':'interrupted','records':[],'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()};_save(cp,receipt)
        receipt=remote.fetch_public('bizinfo',date,None);receipt.update(date=date,attempt=1,origin='mini1_https');_save(cp,receipt)
    biz_rows=receipt.get('records',[]) if receipt.get('status')=='ok' else []
    biz_valid=[v for row in biz_rows if (v:=_normal(row)) is not None]
    biz_unique={v['id']:v for v in biz_valid};invalid=len(biz_rows)-len(biz_valid);duplicates=len(biz_valid)-len(biz_unique)
    biz_status=receipt.get('status','failed')
    if invalid:biz_status='partial' if biz_valid else 'failed'
    if biz_status=='fetching':biz_status='failed'
    sources.append({'id':'bizinfo','name':'기업마당','url':BASE,'origin':'mini1_https','status':biz_status,'count':len(biz_rows) if receipt.get('status')=='ok' else None,'invalid_count':invalid,'duplicate_count':duplicates,'checked_at':receipt.get('checked_at'),'reason_code':'invalid_records' if invalid else receipt.get('reason_code')})
    data_by_source={'bizinfo':list(biz_unique.values())}
    for source in ('msit','koneps'):
        records=[];receipts=[];keywords=[None] if source=='msit' else list(remote.KEYWORDS)
        for i,keyword in enumerate(keywords):
            cp=root/'private'/f'{date}-{source}-{i:02d}.json'
            if cp.exists():receipt=json.loads(cp.read_text())
            else:
                receipt={'date':date,'source':source,'keyword':keyword,'attempt':1,'status':'fetching','reason_code':'interrupted','records':[],'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()}
                _save(cp,receipt)
                receipt=remote.fetch_public(source,date,keyword);receipt.update(date=date,keyword=keyword,attempt=1)
                _save(cp,receipt)
            receipts.append(receipt)
            if receipt.get('status')=='ok':records.extend(receipt.get('records',[]))
            if receipt.get('status')=='auth_required':break
        unique={};invalid_count=0;duplicate_count=0
        for row in records:
            item=_public_normal(source,row)
            if not item:invalid_count+=1;continue
            if item['id'] in unique:duplicate_count+=1
            unique[item['id']]=item
        data_by_source[source]=list(unique.values())
        statuses={r.get('status') for r in receipts}
        status='ok' if len(receipts)==len(keywords) and statuses=={'ok'} else ('auth_required' if 'auth_required' in statuses else 'failed')
        if invalid_count:status='partial' if unique else 'failed'
        sources.append({'id':source,'name':'과학기술정보통신부' if source=='msit' else '나라장터','url':'https://www.msit.go.kr/' if source=='msit' else 'https://www.g2b.go.kr/','status':status,'origin':'mini1_https','count':len(records),'invalid_count':invalid_count,'duplicate_count':duplicate_count,'checked_at':receipts[-1].get('checked_at') if receipts else None,'reason_code':None if status=='ok' else ('invalid_records' if invalid_count else next((r.get('reason_code') for r in receipts if r.get('status')!='ok'),'incomplete'))})
    for source in ('bizinfo','msit','koneps'):
        items=data_by_source[source];previous=_prior(root,date) if source=='bizinfo' else _prior_public(root,date,source);baseline=previous is None;baselines[source]=baseline
        relevant=[i for i in items if _relevant(i)];eligible=[]
        for item in relevant:
            labels=[];note=''
            if not baseline:
                if item['id'] not in previous:labels.append('첫 확인')
                elif _hash(item)!=previous[item['id']]:labels.append('변경');note='공고 정보가 이전 수집본과 달라졌습니다.'
            end=_deadline(item['application_period'])
            if end and 0<=(end-dt.date.fromisoformat(date)).days<=7:labels.append('마감임박')
            if '취소' in item['title']:labels.append('취소')
            if baseline or labels:eligible.append({**item,'labels':labels,'change_note':note})
        _rank(eligible);all_items.extend(eligible)
        source_row=next(x for x in sources if x['id']==source)
        metrics_by_source[source]={'fetched_count':source_row.get('count') or 0,'validated_count':len(items),'invalid_count':source_row.get('invalid_count',0),'duplicate_count':source_row.get('duplicate_count',0),'relevant_count':len(relevant),'shown_count':0,'baseline':baseline}
    _rank(all_items);shown=[]
    for source in ('기업마당','과학기술정보통신부','나라장터'):
        match=next((i for i in all_items if i['source_name']==source),None)
        if match:shown.append(match)
    for item in all_items:
        if len(shown)>=10:break
        if item not in shown:shown.append(item)
    source_ids={'기업마당':'bizinfo','과학기술정보통신부':'msit','나라장터':'koneps'}
    for i in shown:metrics_by_source[source_ids[i['source_name']]]['shown_count']+=1
    result={'selection_revision':3,'date':date,'status':'complete' if all(x['status']=='ok' for x in sources) else 'partial','checked_at':checked,'items':shown,'sources':sources,'metrics':{'sample_limit':200,'comparison_scope':'출처별 최근 수집 표본 비교','fetched_count':sum(x['fetched_count'] for x in metrics_by_source.values()),'relevant_count':sum(x['relevant_count'] for x in metrics_by_source.values()),'shown_count':len(shown),'by_source':metrics_by_source},'baseline':all(baselines.values()),'source_baselines':baselines}
    _save(out,result);_repair_checked_at(result,out);state.update(status='complete',coverage={x['id']:x['status'] for x in sources},completed_at=dt.datetime.now(dt.timezone.utc).isoformat());_save(root/'runs'/(date+'.json'),state);return result

def run(date,*,root=ROOT):
    root=Path(root);dt.date.fromisoformat(date);runs=root/'runs';runs.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (runs/(date+'.lock')).open('a') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        path=runs/(date+'.json');out=root/'editions'/(date+'.json')
        state=json.loads(path.read_text()) if path.exists() else None
        if state and state.get('status') in ('pending','dispatching'):
            raise RuntimeError('previous_submission_uncertain')
        if state and state.get('status')=='failed':raise RuntimeError('review_required')
        if state is None:
            state={'date':date,'status':'local_preparing','attempts':[]}
            placeholder={'date':date,'status':'partial','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'items':[],'sources':[]}
            _save(out,placeholder);_save(path,state)
        if not out.exists():raise RuntimeError('completed_edition_missing')
        existing=json.loads(out.read_text())
        if existing.get('status')=='complete' and existing.get('selection_revision')==3 and {x.get('id') for x in existing.get('sources',[]) if x.get('status')=='ok' and x.get('origin')=='mini1_https'}=={'bizinfo','msit','koneps'}:
            return _repair_checked_at(existing,out)
        return _expand(date,root,state,out)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--date',default=dt.datetime.now(KST).date().isoformat());a=parser.parse_args()
    try:result=run(a.date)
    except (remote.Pending,remote.Failed,RuntimeError) as e:print(json.dumps({'date':a.date,'status':'pending' if isinstance(e,remote.Pending) else 'failed','reason_code':str(e)}));raise SystemExit(2)
    print(json.dumps({'date':a.date,'status':result['status'],'metrics':result['metrics']},ensure_ascii=False))
if __name__=='__main__':main()
