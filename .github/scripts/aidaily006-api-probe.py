"""One read-only credential check; outputs only a sanitised receipt."""
import datetime,json,os,urllib.request,urllib.parse,urllib.error,hashlib
key=os.environ.get('BIZINFO_API_KEY','')
r={'work_id':'AIDAILY-006','tested_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'기업마당','method':'GET','endpoint':'https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do','execution_environment':'GitHub Actions','credential_present':bool(key),'success':False,'attempts':0,'no_automatic_retries':True}
if not key:r['classification']='credential_missing'
else:
 url=r['endpoint']+'?'+urllib.parse.urlencode({'crtfcKey':key,'dataType':'json','searchCnt':5})
 try:
  r['attempts']=1
  req=urllib.request.Request(url,headers={'User-Agent':'AI-Daily-Gov-API-Check/1.0','Accept':'application/json'})
  # Redirects are rejected so the credential is never forwarded elsewhere.
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args,**kwargs):return None
  with urllib.request.build_opener(NoRedirect).open(req,timeout=40)as response:
   r['http_status']=response.status; raw=response.read(2_000_000)
  r['response_sha256']=hashlib.sha256(raw).hexdigest()
  try:data=json.loads(raw.decode('utf-8-sig'))
  except (ValueError,UnicodeError):r['classification']='invalid_json';data={}
  if isinstance(data,dict):
   r['response_fields']=sorted(data.keys())[:20];rows=data.get('jsonArray',[])
   if isinstance(rows,dict):rows=rows.get('item',[])
   if isinstance(rows,dict):rows=[rows]
   valid=[]
   for row in rows if isinstance(rows,list)else[]:
    if not isinstance(row,dict):continue
    title=row.get('pblancNm')or row.get('title');link=row.get('pblancUrl')or row.get('link')
    if not isinstance(title,str)or not title.strip()or not isinstance(link,str):continue
    link=urllib.parse.urljoin('https://www.bizinfo.go.kr/',link.strip());p=urllib.parse.urlsplit(link)
    if p.scheme!='https' or p.hostname not in ('www.bizinfo.go.kr','bizinfo.go.kr'):continue
    valid.append({'title':title.replace(key,'[redacted]')[:240],'url':link.replace(key,'[redacted]'),'published_at':str(row.get('creatPnttm')or row.get('pubDate')or'')[:40]})
   r['valid_announcements']=len(valid);r['samples']=valid[:2];r['success']=bool(valid)and r.get('http_status')==200
   if r['success']:r['classification']='authenticated_data_returned'
   elif 'classification'not in r:
    # Classify business error without logging any raw key-reflecting message.
    text=json.dumps(data,ensure_ascii=False).lower()
    if any(s in text for s in ['인증','키가','key','권한']):r['classification']='authentication_or_registration_required'
    else:r['classification']='no_valid_announcements'
  else:r['classification']='unexpected_schema'
 except urllib.error.HTTPError as exc:r.update(http_status=exc.code,classification='authentication_or_http_refused'if exc.code in (401,403)else'http_error')
 except Exception as exc:r.update(classification='transport_error',error_type=type(exc).__name__)
with open('receipt.json','w')as f:json.dump(r,f,ensure_ascii=False,indent=2)
print(json.dumps(r,ensure_ascii=False))
