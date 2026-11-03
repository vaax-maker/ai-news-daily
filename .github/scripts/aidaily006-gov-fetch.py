"""One bounded Bizinfo GET; artifact contains whitelisted public fields only."""
import datetime as dt
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT='https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do'
FIELDS=('pblancId','pblancNm','title','pblancUrl','link','jrsdInsttNm','excInsttNm','author','creatPnttm','pubDate','bsnsSumryCn','description','reqstBeginEndDe','reqstDt')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    key=os.environ.get('BIZINFO_API_KEY','')
    result={'source':'bizinfo','status':'failed','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'records':[],'response_sha256':None,'reason_code':'unknown'}
    if not key:result['reason_code']='auth_required'
    else:
        try:
            url=ENDPOINT+'?'+urllib.parse.urlencode({'crtfcKey':key,'dataType':'json','searchCnt':200})
            request=urllib.request.Request(url,headers={'User-Agent':'AI-Daily-Gov/1.0','Accept':'application/json'})
            with urllib.request.build_opener(NoRedirect).open(request,timeout=40) as response:
                raw=response.read(8_000_001)
            if len(raw)>8_000_000:raise ValueError('response too large')
            result['response_sha256']=hashlib.sha256(raw).hexdigest()
            payload=json.loads(raw.decode('utf-8-sig'))
            if isinstance(payload,dict) and payload.get('reqErr'):
                result['reason_code']='auth_required'
                raise PermissionError('remote authentication rejected')
            if not isinstance(payload,dict) or 'jsonArray' not in payload:raise ValueError('unexpected schema')
            rows=payload['jsonArray']
            if isinstance(rows,dict):rows=rows.get('item',[])
            if isinstance(rows,dict):rows=[rows]
            if not isinstance(rows,list):raise ValueError('invalid item list')
            records=[]
            for row in rows[:200]:
                if not isinstance(row,dict):continue
                item={}
                for name in FIELDS:
                    value=row.get(name)
                    if isinstance(value,str):item[name]=value.replace(key,'[redacted]')[:5000]
                records.append(item)
            result.update(status='ok',records=records,reason_code=None)
        except PermissionError:result['reason_code']='auth_required'
        except urllib.error.HTTPError as e:
            result['reason_code']='auth_required' if e.code in (401,403) else 'http_error'
        except (ValueError,TypeError,UnicodeError):result['reason_code']='invalid_response'
        except Exception:result['reason_code']='transport_error'
    Path('gov-snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if result['status']!='ok':raise SystemExit(1)
if __name__=='__main__':main()
