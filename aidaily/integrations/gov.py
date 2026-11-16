"""Government HTTPS APIs on mini1; remote helpers remain for historical compatibility."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import tempfile

REPOSITORY='vaax-maker/ai-news-daily'
WORKFLOW='aidaily006-gov-fetch.yml'
ARTIFACT='aidaily006-gov-snapshot'

class Pending(RuntimeError):pass
class Failed(RuntimeError):pass

def _gh(args, *, timeout=35):
    try:
        p=subprocess.run(['gh',*args],capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):raise Pending('transport_uncertain') from None
    if p.returncode:raise Pending('transport_unavailable')
    return p.stdout

def dispatch(request_id):
    # Caller must persist submission intent before this method. Never retry it
    # automatically if exit/transport status is uncertain.
    _gh(['workflow','run',WORKFLOW,'--repo',REPOSITORY,'--ref','main','-f','request_id='+request_id])

def lookup(request_id):
    text=_gh(['run','list','--repo',REPOSITORY,'--workflow',WORKFLOW,'--limit','100','--json','databaseId,displayTitle,status,conclusion'])
    try:rows=json.loads(text)
    except ValueError:raise Pending('invalid_run_list') from None
    matches=[r for r in rows if r.get('displayTitle')=='AIDAILY006-'+request_id]
    if len(matches)>1:raise Failed('duplicate_request_id')
    if not matches:raise Pending('run_not_visible')
    row=matches[0]
    if row.get('status')!='completed':raise Pending('run_pending')
    run_id=row.get('databaseId')
    if not isinstance(run_id,int):raise Failed('invalid_run_id')
    # Failed jobs can still upload a sanitised failure artifact.
    with tempfile.TemporaryDirectory(prefix='aidaily-gov-') as temp:
        os.chmod(temp,0o700)
        try:_gh(['run','download',str(run_id),'--repo',REPOSITORY,'--name',ARTIFACT,'--dir',temp])
        except Pending:
            if row.get('conclusion')!='success':raise Failed('remote_job_failed') from None
            raise
        path=Path(temp)/'gov-snapshot.json'
        try:payload=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise Failed('invalid_snapshot') from None
    if not isinstance(payload,dict) or payload.get('source')!='bizinfo':raise Failed('invalid_snapshot')
    if payload.get('status')!='ok':
        reason=payload.get('reason_code')
        raise Failed(reason if reason in ('auth_required','http_error','invalid_response','transport_error') else 'remote_failed')
    if row.get('conclusion')!='success':raise Failed('remote_job_failed')
    if not isinstance(payload.get('records'),list) or len(payload['records'])>200:raise Failed('invalid_snapshot')
    if not isinstance(payload.get('response_sha256'),str) or len(payload['response_sha256'])!=64 or any(c not in '0123456789abcdef' for c in payload['response_sha256']):raise Failed('invalid_snapshot')
    if not isinstance(payload.get('checked_at'),str) or len(payload['checked_at'])>40:raise Failed('invalid_snapshot')
    return run_id,payload

# Public-data direct HTTPS integration. Never log credential-bearing URLs.
KEYWORDS=('인공지능 개발','머신러닝','딥러닝','메타버스','가상현실','증강현실','디지털트윈','XR 콘텐츠','실감콘텐츠','실감미디어','영상콘텐츠','뉴미디어','미디어 플랫폼','IDC','데이터센터','클라우드')
ENDPOINTS={'bizinfo':'https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do','msit':'https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList','koneps':'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'}
FIELDS={'bizinfo':('pblancId','pblancNm','title','pblancUrl','link','jrsdInsttNm','excInsttNm','author','creatPnttm','pubDate','bsnsSumryCn','description','reqstBeginEndDe','reqstDt'),'msit':('subject','viewUrl','deptName','pressDt'),'koneps':('bidNtceDtlUrl','bidNtceNm','bidNtceNo','bidNtceOrd','bidNtceDt','bidBeginDt','bidClseDt','dminsttNm','ntceInsttNm')}

def _public_key():
    import urllib.parse
    value=os.environ.get('GOV_API_KEY','')
    if not value:
        try:value=json.loads((Path.home()/'.config/aidaily/gov-api.json').read_text()).get('GOV_API_KEY','')
        except (OSError,ValueError,AttributeError):return ''
    return urllib.parse.unquote(value) if isinstance(value,str) else ''

def _biz_key():
    value=os.environ.get('BIZINFO_API_KEY','')
    if not value:
        try:value=json.loads((Path.home()/'.config/aidaily/gov-api.json').read_text()).get('BIZINFO_API_KEY','')
        except (OSError,ValueError,AttributeError):return ''
    return value if isinstance(value,str) else ''


def fetch_public(source,date,keyword=None):
    import datetime as dt,hashlib,urllib.parse,urllib.request,urllib.error,xml.etree.ElementTree as ET
    if source not in ENDPOINTS or (source=='koneps' and keyword not in KEYWORDS):raise ValueError('invalid_source')
    now=dt.datetime.now(dt.timezone.utc).isoformat();result={'source':source,'status':'failed','reason_code':'unknown','checked_at':now,'records':[],'response_sha256':None}
    key=_biz_key() if source=='bizinfo' else _public_key()
    if not key:result['status']='auth_required';result['reason_code']='credential_missing';return result
    day=dt.date.fromisoformat(date)
    if source=='bizinfo':params={'dataType':'json','searchCnt':200}
    elif source=='msit':params={'numOfRows':30,'pageNo':1,'type':'xml'}
    else:
        local_now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
        end=local_now.strftime('%Y%m%d%H%M') if day==local_now.date() else day.strftime('%Y%m%d')+'2359'
        params={'numOfRows':10,'pageNo':1,'type':'json','inqryDiv':'1','inqryBgnDt':(day-dt.timedelta(days=7)).strftime('%Y%m%d')+'0000','inqryEndDt':end,'bidNtceNm':keyword}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    try:
        url=ENDPOINTS[source]+'?'+urllib.parse.urlencode({('crtfcKey' if source=='bizinfo' else 'serviceKey'):key,**params})
        request=urllib.request.Request(url,headers={'User-Agent':'AI-Daily-Gov/1.0','Accept':'application/json, application/xml'})
        with urllib.request.build_opener(NoRedirect).open(request,timeout=30) as response:raw=response.read(8_000_001)
        if len(raw)>8_000_000:raise ValueError('too_large')
        result['response_sha256']=hashlib.sha256(raw).hexdigest()
        if source=='bizinfo':
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('invalid_items')
            if data.get('reqErr'):
                result.update(status='auth_required',reason_code='api_rejected');return result
            if 'jsonArray' not in data:raise ValueError('invalid_items')
            rows=data['jsonArray']
            if isinstance(rows,dict):rows=rows.get('item',[])
            if isinstance(rows,dict):rows=[rows]
            if not isinstance(rows,list):raise ValueError('invalid_items')
            rows=rows[:200];code='00'
        elif source=='msit':
            root=ET.fromstring(raw);tag=lambda x:x.tag.split('}')[-1]
            code=next(((x.text or '') for x in root.iter() if tag(x) in ('resultCode','returnReasonCode')),'')
            rows=[{tag(child):child.text or '' for child in x} for x in root.iter() if tag(x)=='item']
        else:
            data=json.loads(raw);resp=data.get('response',{});head=resp.get('header',{});body=resp.get('body',{})
            code=str(head.get('resultCode',''));rows=body.get('items',[]) if isinstance(body,dict) else []
            if isinstance(rows,dict):rows=rows.get('item',[])
            if isinstance(rows,dict):rows=[rows]
            if not isinstance(rows,list):raise ValueError('invalid_items')
        if str(code) not in ('00','0','0000'):
            result.update(status='auth_required' if str(code) in ('20','30','31','32','33') else 'failed',reason_code='api_rejected');return result
        records=[]
        for row in rows:
            if not isinstance(row,dict):continue
            records.append({field:str(row[field]).replace(key,'[redacted]')[:5000] for field in FIELDS[source] if isinstance(row.get(field),(str,int,float))})
        result.update(status='ok',reason_code=None,records=records);return result
    except urllib.error.HTTPError as e:result.update(status='auth_required' if e.code in (401,403) else 'failed',reason_code='http_error')
    except (ValueError,TypeError,ET.ParseError):result['reason_code']='invalid_response'
    except Exception:result['reason_code']='transport_error'
    return result
