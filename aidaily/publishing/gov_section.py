"""Whitelisted government notices in the existing technical daily page."""
from __future__ import annotations
import datetime as dt
import html
import json
import re
from urllib.parse import urlsplit, parse_qs, urlencode
from pathlib import Path
from aidaily import config
from aidaily.publishing.horizon_section import safe_url

CSS='''
.gov-updates{margin-top:26px;min-width:0;overflow-wrap:anywhere}
.gov-updates h2{margin:0}
.gov-updates a:focus-visible,.gov-updates summary:focus-visible,.gov-table-wrap:focus-visible{outline:2px solid currentColor;outline-offset:3px}
.gov-updates .gov-intro{font-size:12px;line-height:1.85}
.gov-table-wrap{width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-x:contain}
.gov-table{width:100%;min-width:620px;border-collapse:collapse;table-layout:fixed;font-size:13px;line-height:1.65;text-align:left}
.gov-table caption{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.gov-table th,.gov-table td{padding:12px 10px;border-bottom:1px solid var(--gov-line);vertical-align:top;overflow-wrap:anywhere}
.gov-table th{font-weight:750;font-size:12px;white-space:nowrap}
.gov-table td a{color:var(--gov-link);font-size:14px;font-weight:650;text-decoration:underline;text-underline-offset:3px}
.gov-col-date{width:110px}.gov-col-source{width:100px}.gov-col-agency{width:150px}
.gov-date span{display:block;white-space:nowrap;font-variant-numeric:tabular-nums}
.gov-updates details{font-size:12px;line-height:1.9;margin-top:12px}
.gov-scroll-hint{display:none;font-size:12px;line-height:1.7}
@media(max-width:640px){.gov-scroll-hint{display:block;font-weight:600}.gov-table{min-width:540px;font-size:13px}.gov-table th,.gov-table td{padding:10px 8px}.gov-col-date{width:94px}.gov-col-source{width:76px}.gov-col-agency{width:102px}.gov-date{font-size:12.5px}.gov-table td:nth-child(2){font-size:12px}.gov-table td a{font-size:14px}.gov-updates details{font-size:12.5px}}
'''
STATUS={'complete','partial','failed','pending','invalid','running'}
def public_url(value, *, notice=False):
 if not safe_url(value):return ''
 p=urlsplit(value)
 if p.scheme!='https' or p.port not in (None,443) or p.fragment:return ''
 if notice:
  query=parse_qs(p.query,keep_blank_values=True)
  if any(len(values)!=1 for values in query.values()):return ''
  if p.hostname=='www.bizinfo.go.kr':
   if p.path!='/sii/siia/selectSIIA200Detail.do' or set(query)!={'pblancId'}:return ''
   if not re.fullmatch(r'PBLN_[A-Za-z0-9_-]{1,70}',query['pblancId'][0]):return ''
  elif p.hostname=='www.msit.go.kr':
   if p.path!='/bbs/view.do' or set(query)!={'sCode','mId','mPid','bbsSeqNo','nttSeqNo'} or query['sCode']!=['user']:return ''
   if any(not re.fullmatch(r'\d{1,24}',query[k][0])for k in ('mId','mPid','bbsSeqNo','nttSeqNo')):return ''
  elif p.hostname=='www.g2b.go.kr':
   if p.path!='/link/PNPE027_01/single/'or set(query)!={'bidPbancNo','bidPbancOrd'}:return ''
   if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',query['bidPbancNo'][0])or not re.fullmatch(r'\d{1,10}',query['bidPbancOrd'][0]):return ''
  else:return ''
  return 'https://'+p.hostname+p.path+'?'+urlencode({k:v[0]for k,v in query.items()})
 if p.hostname not in ('www.bizinfo.go.kr','www.msit.go.kr','www.g2b.go.kr')or p.path not in ('','/')or p.query:return ''
 return 'https://'+p.hostname+'/'

def text(v):return v.strip() if isinstance(v,str)else''

def checked_label(value):
 try:
  date=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  if date.tzinfo is None:return ''
  return date.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime('%Y.%m.%d %H:%M KST')
 except (ValueError,TypeError,AttributeError):return ''

def normalize_edition(data,date):
 if not isinstance(data,dict)or data.get('date')!=date or data.get('status')not in STATUS:raise ValueError('Invalid government edition')
 result={'date':date,'status':data['status'],'checked_at':text(data.get('checked_at')),'baseline':data.get('baseline')is True,'items':[],'sources':[],'metrics':{}}
 ids=set()
 for row in data.get('items')or[]:
  if not isinstance(row,dict):raise ValueError('Invalid government notice')
  identity=text(row.get('id'));url=public_url(row.get('url'),notice=True);title=text(row.get('title'))
  if not identity or identity in ids or not url or not title:raise ValueError('Invalid duplicate government notice or URL')
  parts=urlsplit(url);q=parse_qs(parts.query)
  expected=q['pblancId'][0]if parts.hostname=='www.bizinfo.go.kr'else 'msit:'+q['bbsSeqNo'][0]+':'+q['nttSeqNo'][0]if parts.hostname=='www.msit.go.kr'else 'koneps:'+q['bidPbancNo'][0]+':'+q['bidPbancOrd'][0]
  if expected!=identity:raise ValueError('Government identity differs from original')
  ids.add(identity)
  item={k:text(row.get(k))for k in ('id','title','source_name','agency','published_date','published_at','application_period','summary','change_note')};item['url']=url
  item['source_name']={'www.bizinfo.go.kr':'기업마당','www.msit.go.kr':'과학기술정보통신부','www.g2b.go.kr':'나라장터'}[parts.hostname]
  item['notice_kind']='취소공고'if '취소'in item['title']else'선정결과'if re.search(r'선정\s*결과',item['title'])else'용역입찰'if parts.hostname=='www.g2b.go.kr'else'지원사업'if parts.hostname=='www.bizinfo.go.kr'else'사업공고'
  item['labels']=[x for x in row.get('labels',[])if x in ('기준판','신규','변경','마감 임박','마감임박','접수중','첫 확인')]
  result['items'].append(item)
 if len(result['items'])>20:raise ValueError('Too many government notices')
 for row in data.get('sources')or[]:
  if not isinstance(row,dict):continue
  url=public_url(row.get('url'));name=text(row.get('name'))
  if not url or not name:continue
  result['sources'].append({k:text(row.get(k))for k in ('id','name','status','checked_at')}|{'url':url,'count':row.get('count')if type(row.get('count'))is int and row['count']>=0 else None})
 result['source_baselines']={k:v for k,v in (data.get('source_baselines')or{}).items()if k in ('bizinfo','msit','koneps')and type(v)is bool}
 result['metrics']['by_source']={}
 for source,metrics in (data.get('metrics',{}).get('by_source')or{}).items():
  if source in ('bizinfo','msit','koneps')and isinstance(metrics,dict):result['metrics']['by_source'][source]={k:v for k,v in metrics.items()if k in ('fetched_count','validated_count','invalid_count','duplicate_count','relevant_count','shown_count')and type(v)is int and v>=0}
 for key in ('fetched_count','relevant_count','shown_count'):
  if type((data.get('metrics')or{}).get(key))is int:result['metrics'][key]=data['metrics'][key]
 if result['status']=='complete'and any(s['status']not in ('ok','complete')for s in result['sources']):result['status']='partial'
 return result

def load_editions(root=None):
 root=Path(root)if root is not None else config.DATA_ROOT/'ai_news/gov';out={}
 for path in (root/'editions').glob('????-??-??.json'):
  try:dt.date.fromisoformat(path.stem)
  except ValueError:continue
  try:out[path.stem]=normalize_edition(json.loads(path.read_text()),path.stem)
  except (OSError,ValueError,TypeError,KeyError):out[path.stem]={'date':path.stem,'status':'invalid','items':[],'sources':[],'metrics':{}}
 for path in (root/'runs').glob('????-??-??.json'):
  if path.stem in out:continue
  try:
   dt.date.fromisoformat(path.stem);data=json.loads(path.read_text());status=data.get('status','pending')
   if status not in STATUS:status='pending'if status in ('submitted','dispatching','submission_unknown','waiting','queued','in_progress')else'failed'
   out[path.stem]={'date':path.stem,'status':status,'items':[],'sources':[],'metrics':{}}
  except (OSError,ValueError,TypeError):continue
 return out

def source_display(item):
 return {'과학기술정보통신부':'과기정통부'}.get(item.get('source_name'),item.get('source_name')or'출처 미확인')

def notice_time(item):
 value=text(item.get('published_at'))or text(item.get('published_date'))
 if not value:return '미제공'
 try:
  date=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  if date.tzinfo is not None:date=date.astimezone(dt.timezone(dt.timedelta(hours=9)))
  if not re.search(r'\d{1,2}:\d{2}',value):return date.strftime('%Y.%m.%d')
  return date.strftime('%Y.%m.%d %H:%M:%S'if re.search(r'\d{1,2}:\d{2}:\d{2}',value)else'%Y.%m.%d %H:%M')
 except ValueError:return value[:60]

def render_section(edition,date,tokens):
 C=tokens['color'];ink=C['text']['tech.ink'];dim=C['text']['tech.dim'];line=C['line']['tech'];tone=C['accent']['tech'];e=html.escape
 data=edition if isinstance(edition,dict)and edition.get('date')==date else{'status':'absent','items':[],'sources':[],'metrics':{}}
 status=data['status'];items=data.get('items',[])if status in ('complete','partial')else[]
 messages={'absent':'이 날짜의 정부과제 기록이 없습니다.','pending':'공고를 확인하고 있습니다.','running':'공고를 확인하고 있습니다.','failed':'공고를 확인하지 못했습니다. 아래 공식 출처에서 확인해 주세요.','invalid':'이 날짜의 공고 기록을 불러오지 못했습니다.'}
 notice=messages.get(status,'')
 if status=='partial':notice='일부 출처는 아직 확인하지 못했습니다. 확인된 자료부터 보여드립니다.'
 if status in ('complete','partial')and not items:notice+=' 확인한 범위에서 표시할 대상 공고가 없습니다.'
 intro='첫 확인 자료를 비교 기준으로 저장했습니다. 오늘 새로 나온 공고라는 뜻은 아닙니다.'if data.get('baseline')else'일시는 출처가 제공한 등록·게시·공고 시각이며, 시각이 없으면 날짜만 표시합니다.'
 if status not in ('complete','partial'):intro='선택한 날짜에 확인한 정부 지원사업과 용역 공고를 모읍니다.'
 rows=[]
 for item in items:
  when=notice_time(item);parts=when.split(' ',1);stamp='<span>'+e(parts[0])+'</span>'+('<span>'+e(parts[1])+'</span>'if len(parts)==2 else'')
  agency=item.get('agency')or'기관 미확인'
  rows.append('<tr data-gov-item="'+e(item['id'],quote=True)+'"><td class="gov-date">'+stamp+'</td><td title="'+e(item.get('source_name')or'',quote=True)+'">'+e(source_display(item))+'</td><td>'+e(agency)+'</td><td><a href="'+e(item['url'],quote=True)+'" target="_blank" rel="noopener noreferrer" aria-label="'+e(item['title']+' — 공식 원문, 새 창',quote=True)+'">'+e(item['title'])+'</a></td></tr>')
 table='<div class="gov-table-wrap" role="region" aria-label="정부과제 공고 표, 좌우 이동 가능" tabindex="0"><table class="gov-table"><caption>정부과제 공고 목록</caption><colgroup><col class="gov-col-date"><col class="gov-col-source"><col class="gov-col-agency"><col></colgroup><thead><tr>'+''.join('<th scope="col">'+x+'</th>'for x in ('일시','출처','기관명','제목'))+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
 sources=[]
 for source in data.get('sources',[]):
  label='확인 완료'if source['status']in ('ok','complete')else'확인 준비 중'if source['status']=='auth_required'else'일부 자료 확인'if source['status']=='partial'else'확인하지 못함'
  if source.get('count')is not None:label+=' · '+str(source['count'])+'건 조회'
  metrics=data.get('metrics',{}).get('by_source',{}).get(source.get('id'),{})
  if metrics:label+=' · 관련 '+str(metrics.get('relevant_count',0))+'건 · 표시 '+str(metrics.get('shown_count',0))+'건'
  source_time=checked_label(source.get('checked_at'))
  if source_time:label+=' · '+source_time
  if metrics.get('invalid_count'):label+=' · 검증 제외 '+str(metrics['invalid_count'])+'건'
  sources.append('<li><a href="'+e(source['url'],quote=True)+'" target="_blank" rel="noopener noreferrer">'+e(source['name'])+'</a> · '+label+'</li>')
 if not sources:sources=['<li><a href="https://www.bizinfo.go.kr/" target="_blank" rel="noopener noreferrer">기업마당 공식 홈페이지</a></li>']
 label=checked_label(data.get('checked_at'));checked=' · 최종 확인 '+e(label)if label else''
 count=' · '+str(len(items))+'건'if status in ('complete','partial')else''
 return '<section id="gov-updates" class="gov-updates" data-gov-date="'+e(date,quote=True)+'" data-gov-status="'+e(status)+'" style="--gov-line:'+line+';--gov-link:'+tone+';color:'+ink+'"><div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;padding-bottom:12px;border-bottom:1px solid '+ink+'"><h2 style="font-size:15px;font-weight:800;color:'+tone+'">정부과제 일일업데이트</h2><span style="font-size:11.5px;color:'+dim+'">테스트 · '+e(date)+count+'</span></div><p class="gov-intro" style="color:'+dim+'">'+intro+'</p>'+('<p role="status" class="gov-intro" style="color:'+dim+'">'+e(notice)+'</p>'if notice else'')+'<p class="gov-scroll-hint">← 표를 좌우로 밀어 제목까지 확인하세요 →</p><div style="color:'+dim+'">'+table+'</div><details style="color:'+dim+'"><summary>살펴본 출처와 확인 범위</summary><ul>'+''.join(sources)+'</ul><p>기업마당 최근 최대 200건, 과기정통부 최신 사업공고, 나라장터 최근 7일의 지정 기술 키워드 검색 표본입니다. 일시는 기업마당 등록일시·과기정통부 게시일·나라장터 공고일시를 뜻하며, 제공되지 않은 시각은 붙이지 않습니다. 전체 공고의 전수 조사 결과는 아닙니다.'+checked+'</p></details></section>'
