"""Resumable rolling newsroom: collect -> research -> draft -> review -> materialize.

External publication and notifications remain in aidaily.publishing/notifications.
"""
from __future__ import annotations
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import copy
from aidaily import config
from aidaily.integrations import openrouter, public_research
from aidaily.customer_stories import rolling_inputs, newsroom_topics
from aidaily.customer_stories.story_pipeline import EDITOR_SYSTEM, validate_report

SETTINGS = dict(enabled=False,window_days=14,maximum_candidate_fragments=8,
                selection=dict(minimum_observations=2,minimum_days=2,minimum_sources=2,maximum_topics=2),
                public_search=True)

def settings_path():return config.DATA_ROOT/'customer_stories/newsroom-settings.json'
def settings():
 path=settings_path();value={**SETTINGS,**(json.loads(path.read_text())if path.exists()else{})}
 if type(value['window_days'])is not int or not 1<=value['window_days']<=14:raise ValueError('invalid rolling window')
 if type(value['maximum_candidate_fragments'])is not int or not 2<=value['maximum_candidate_fragments']<=100:raise ValueError('invalid fragment budget')
 return value

def save(path,value,private=True):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.new')
 with tmp.open('w')as f:
  if private:os.chmod(tmp,0o600)
  json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 tmp.replace(path)

def parse(raw):
 # Shared LLM may return fenced JSON; preserve the receipt and parse once.
 value=str(raw).strip()
 if value.startswith('```'):value=value.split('\n',1)[1].rsplit('```',1)[0]
 report=json.loads(value)
 if not isinstance(report,dict):raise ValueError('report must be an object')
 return report

RETRY=3  # run() asks its caller to re-enter with the next candidate/tier
PUBLIC_SOURCES=('HN','긱뉴스','Reddit')

def public_pick(dossier,limit=6):
 """Last-resort topic built only from public, unpublished posts (never private rooms)."""
 day=lambda r:(r.get('observed_dates')or[r['date']])[-1]
 rows=[r for r in dossier['evidence']if not r.get('private')and not r['already_published']and r.get('source')in PUBLIC_SOURCES and len(r['text'])>=40]
 rows=sorted(rows,key=day,reverse=True)[:limit]
 if len(rows)<2:return None
 return dict(topic_id='public-pick',service='public-pick',label='이번 주 읽을거리',already_reported=False,new_development=False,research=[],
   observations=[dict(evidence_id=r['evidence_id'],source_id=r['source_id'],date=day(r),kind='question',already_published=False)for r in rows])

def restore_refs(report,evidence_aliases,research_aliases):
 """Resolve short model-facing labels to frozen evidence; never guess a URL."""
 for item in report.get('items',[]):
  for row in [item,*item.get('voices',[]),*item.get('timeline',[])]:
   if 'evidence_ids'in row:row['evidence_ids']=[evidence_aliases.get(ref,ref)for ref in row['evidence_ids']if ref not in research_aliases]  # research labels (F#) are not story evidence
  for fact in item.get('background',[]):
   source=research_aliases.get(fact.get('research_id'))
   if source:fact.update(url=source['url'],source_excerpt=source['text'])
 return report

def check_draft(report,dossier,research,history):
 from aidaily.customer_stories.public_copy_gate import validate_public_copy
 validate_report(report,dossier,research,history)
 validate_public_copy(report,dossier)
 docs={r['url']:r['text']for r in research}
 for item in report['items']:
  for fact in item.get('background',[]):
   quote=fact.get('source_excerpt','')
   if len(quote)<12 or quote not in docs.get(fact.get('url'),''):raise ValueError('public background source excerpt does not match fetched evidence')

def candidate_sample(topic,pool,limit):
 """Prefer unpublished recent observations, with source diversity before repeats."""
 rows=[o for o in topic['observations']if o['kind']!='promotion']
 rows.sort(key=lambda o:(o['already_published'],-dt.date.fromisoformat(o['date']).toordinal(),not pool[o['evidence_id']].get('private',False),o['evidence_id']))
 first=[];remaining=[];seen=set()
 for row in rows:
  if row['source_id']in seen:remaining.append(row)
  else:first.append(row);seen.add(row['source_id'])
 ordered=sorted(first+remaining,key=lambda o:o['already_published'])
 return ordered[:limit]

MODEL_EDITOR_SYSTEM=EDITOR_SYSTEM.replace('URL을 붙인다.','제공된 research_id를 붙인다.').replace('"background":[{"text":str,"url":str,"label":str}]','"background":[{"text":str,"research_id":str,"label":str}]')

def review_packet(report,prompt):
 """Keep the full relevant source body once; omit duplicate verification metadata."""
 article=copy.deepcopy(report)
 cited={eid for item in article['items']for eid in item['evidence_ids']}
 urls={fact['url']for item in article['items']for fact in item.get('background',[])}
 for item in article['items']:
  for fact in item.get('background',[]):fact.pop('source_excerpt',None)
 return {'report':article,'evidence':[r for r in prompt['evidence']if r['evidence_id']in cited],
  'research':list({(r['url'],r['text']):r for r in prompt['research']if r['url']in urls}.values()),'history':prompt['previous_publications']}

def public_copy(report):
 from aidaily.customer_stories.pipeline import public_story_text,public_source_label
 from aidaily.customer_stories.story_render import safe_url
 # Never send source excerpts/private verification text into docs or feed.
 allowed=('text','url','label','source','date','stage')
 result={k:public_story_text(str(report.get(k)or'')) for k in ('title','overview')};result.update(schema_version=2,mood='',items=[])
 for index,item in enumerate(report.get('items',[])):
  row={k:public_story_text(str(item.get(k)or'')) for k in ('story_id','issue','dek','commentary','article_kind')}
  # Machine identity was validated as an ASCII slug; prose anonymization must
  # not redact a date suffix and break anchors/publication-history linkage.
  row['story_id']=item['story_id']
  if item.get('publication_index') is not None:row['publication_index']=item['publication_index']
  row['evidence_ids']=item.get('evidence_ids',[])
  row['sources']=list(dict.fromkeys(public_source_label(str(v.get('source')or''))for v in item.get('voices',[])if v.get('source')))
  for field in ('background','voices','timeline','related_links'):
   row[field]=[{k:public_story_text(str(value)) for k,value in v.items()if k in allowed and k!='url'}for v in item.get(field,[])]
   # URLs are identifiers of the already validated public sources, not prose:
   # masking digits in a document path silently breaks the citation. Never copy
   # a URL from a voice or timeline (which may describe private conversations).
   if field in ('background','related_links'):
    for target,original in zip(row[field],item.get(field,[])):
     url=safe_url(original.get('url'))
     if url:target['url']=url
   if field in ('voices','timeline'):
    for v in row[field]:
     try:dt.date.fromisoformat(v.get('date',''))
     except ValueError:continue
     v['date']+=' 수집 관찰일'
   if field=='timeline':
    for v,original in zip(row[field],item.get(field,[])):v['evidence_ids']=original.get('evidence_ids',[])
  result['items'].append(row)
 return result

def materialize(report,date,data_root,docs_root,*,state_id):
 from aidaily.customer_stories.pipeline import render_customer_stories,load_manifest,upsert_manifest,render_archive_index
 root=Path(data_root);docs=Path(docs_root);archive=docs/'v2/uservoice';archive.mkdir(parents=True,exist_ok=True)
 target=root/(date+'.json')
 # Preserve previous edition and page before the intentional format revision.
 backup=root/'newsroom/backups'/state_id
 if target.exists()and not backup.exists():
  backup.mkdir(parents=True,mode=0o700)
  for file in (target,archive/(date+'.html')):
   if file.exists():
    shutil.copy2(file,backup/file.name);(backup/file.name).chmod(0o600)
 gen=public_copy(report)
 payload={'date':date,'gen':gen,'sources':list(dict.fromkeys(s for i in gen['items']for s in i.get('sources',[]))),
          'editorial':{'schema_version':2,'state_id':state_id,'mode':'rolling_newsroom'}}
 save(target,payload);save(root/'latest.json',payload)
 (archive/(date+'.html')).write_text(render_customer_stories(gen,date,in_subdir=True))
 (docs/'v2/uservoice.html').write_text(render_customer_stories(gen,date,in_subdir=False))
 manifest=upsert_manifest(load_manifest(str(archive/'manifest.json')),date,gen)
 save(archive/'manifest.json',manifest,False);(archive/'index.html').write_text(render_archive_index(manifest))
 # A history record reserves generated stories, independent of source collection.
 ledger=root/'newsroom/story-history.json';history=json.loads(ledger.read_text())if ledger.exists()else[]
 for item in report['items']:
  row={'date':date,'story_id':item['story_id'],'issue':item['issue'],'evidence_ids':item['evidence_ids'],
       'status':'generated','content_fingerprint':hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
  history=[h for h in history if not(h['date']==date and h['story_id']==row['story_id'])]+[row]
 save(ledger,history)
 return payload

REVIEW_SYSTEM='''너는 신문 데스크다. 기사·근거·이전 발행 이력을 대조한다. 근거가 지지하지 않는 사실, 개인정보/직접인용,
제품 혼동, 서로 다른 사람을 합성한 이야기, 이미 쓴 사건의 새 사실 없는 재보도, 공식 소개를 성능검증으로 오인,
자료에 담겼다 같은 과정 설명, 반복과 진부한 개요를 점검한다. 질문은 경험으로 바꾸지 않는다.
JSON만 출력: {"ok":true|false,"supported":true|false,"privacy":true|false,"not_duplicate":true|false,"issues":[str]}.
하나라도 위반하면 ok=false. 새로운 해설이 기존에 실리지 않은 사용자 질문을 공식 자료로 설명하면 해설 기사로 검토할 수 있다.'''
REVIEW_SYSTEM+='\nevidence와 research는 공개되는 본문이 아닌 비공개 대조 자료다. 그 필드가 입력에 있다는 이유로 개인정보 위반으로 판정하지 마라. 출처를 익명화하고 우리말로 바꾼 경험/질문 요약은 허용한다. 기사에 없는 정보를 빠뜨렸다는 이유만으로 오류라고 하지 마라.'

def run(args, *, approved_report=None):
 root=config.DATA_ROOT/'customer_stories';directory=root/'newsroom';directory.mkdir(parents=True,exist_ok=True)
 date=args.date;statepath=directory/(date+'.json');opts=settings()
 with (directory/'run.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  state=json.loads(statepath.read_text())if statepath.exists()else{'version':2,'date':date,'stage':'new','settings':opts}
  if state.get('stage')=='complete'and not getattr(args,'reviewed_report',None):return 0
  if getattr(args,'reviewed_report',None):
   if not getattr(args,'review_note',None)or not state.get('dossier'):raise ValueError('desk revision needs a reason and existing frozen input')
   report_path=Path(args.reviewed_report)
   edited=json.loads(report_path.read_text())
   # Editing is a concrete workflow, not permission to skip evidence/privacy or
   # independent desk checks. Preserve the rejected original before replacing it.
   state.setdefault('desk_revisions',[]).append({'before':state.get('report'),'before_stage':state['stage'],
     'note':args.review_note,'sha256':hashlib.sha256(report_path.read_bytes()).hexdigest()})
   cited={ref for item in edited['items']for ref in item['evidence_ids']}
   state['prompt']['evidence']=[{k:r.get(k)for k in ('evidence_id','text','source','date','private','already_published')}
      for r in state['dossier']['evidence']if r['evidence_id']in cited]
   sources={r['url']:r for result in state['research'].values()for r in result['sources']}
   snippets=[]
   for item in edited['items']:
    for fact in item.get('background',[]):
     quote=fact.get('source_excerpt','');document=sources.get(fact.get('url'),{}).get('text','')
     if not quote or quote not in document:raise ValueError('desk background excerpt does not match frozen official source')
     pos=document.index(quote);snippets.append({'url':fact['url'],'text':document[max(0,pos-200):pos+len(quote)+300]})
   state['prompt']['research']=snippets
   state.update(stage='drafted',report=edited,repair_used=True);save(statepath,state)
  if state.get('stage')in ('support_review_required','review_required')and isinstance(state.get('report',{}).get('items'),list)and not state['report']['items']:
   state.update(stage='no_candidates',reason='resumed_empty_article_result');save(statepath,state)
   save(root/('skip-'+date+'.json'),{'date':date,'reason':'근거를 충족한 기사 없음','state_id':date})
   return 2
  opts=state['settings'] # Frozen thresholds/input identity for resumable generation.
  from aidaily.customer_stories.pipeline import _ai_judge_enabled
  # Preserve the project's opt-in blocking judge policy. Deterministic source,
  # privacy and identity checks are mandatory regardless of this setting.
  if state.get('stage')=='review_required'and state.get('review')and state['review'].get('not_duplicate')is True and state['review'].get('supported')is True and not _ai_judge_enabled():
   check_draft(state['report'],state['dossier'],[r for value in state['research'].values()for r in value['sources']],[])
   state.update(stage='reviewed',review_status='advisory');save(statepath,state)
  if state.get('stage')=='review_required'and len(state.get('rejected_candidates',[]))<2:
   failed={'shortlist':state.get('shortlist'), 'report':state.get('report'), 'review':state.get('review'), 'reason':state.get('gate_error','desk_review_failed')}
   state.setdefault('rejected_candidates',[]).append(failed)
   state.setdefault('excluded_topics',[]).extend(state.get('shortlist',{}).get('selected_topic_ids',[]))
   for key in ('report','repair_used','repair_input','review','gate_error','shortlist'):state.pop(key,None)
   state.update(stage='researched');save(statepath,state)
  if state['stage']=='new':
   from aidaily.customer_stories import sources,pipeline
   web=[];collection_errors=[]
   try:
    for values in sources.fetch_all().values():web.extend(values)
   except Exception as error:collection_errors.append(type(error).__name__)
   rooms,_=pipeline.load_jsonl_rooms(hours=24,per_room_chars=24000,seen={})
   dossier=rolling_inputs.gather(root,date,opts['window_days'],extra_web=web,extra_rooms=rooms)
   dossier['coverage']['current_collection_errors']=collection_errors
   dossier['coverage']['private_current_input']='up_to_24000_chars_per_source; upstream280_chars_per_message; sampled'
   # Preserve new V2 evidence history without treating mere collection as publication.
   ledger=directory/'story-history.json';previous=json.loads(ledger.read_text())if ledger.exists()else[]
   consumed={eid for row in previous if row.get('status')=='published' for eid in row.get('evidence_ids',[])}
   for row in dossier['evidence']:
    if row['evidence_id']in consumed:row['already_published']=True
   dossier['story_history']=previous
   state.update(stage='collected',dossier=dossier);save(statepath,state)
  dossier=state['dossier']
  if state['stage']=='collected':
   # Identify public service groups locally before any public search request.
   preliminary,_=newsroom_topics.discovery(dossier,{},opts)
   research={}
   for topic in preliminary:
    research[topic['service']]=public_research.research(topic['service'],search=opts['public_search'])
   topics,selection=newsroom_topics.discovery(dossier,research,opts)
   state.update(stage='researched',research=research,topics=topics,selection=selection);save(statepath,state)
  if state['stage']=='researched':
   # Service groups are discovery buckets, not articles. Let the desk compare
   # new evidence/reader questions before choosing, rather than rank by volume.
   pool={row['evidence_id']:row for row in dossier['evidence']}
   eligible={r['topic_id']for r in state['selection']['candidates']if r['eligible']and r['topic_id']not in state.get('excluded_topics',[])}
   choices=[]
   for topic in state['topics']:
    if topic['topic_id']not in eligible:continue
    fresh=[pool[o['evidence_id']]['text']for o in candidate_sample(topic,pool,8)if not o['already_published']]
    if fresh:choices.append({'topic_id':topic['topic_id'],'label':topic['label'],'new_sample':fresh[:3]})
   if not choices:
    # Daily-coverage tiers (approved 2026-11-08): strict -> relaxed thresholds -> public sources.
    if state.get('tier',0)<1:
     relaxed={**state['settings']['selection'],'minimum_days':1,'minimum_observations':3}
     topics,selection=newsroom_topics.discovery(dossier,state['research'],{**state['settings'],'selection':relaxed})
     state['settings']['selection']=relaxed
     state.update(tier=1,topics=topics,selection=selection);save(statepath,state);return RETRY
    if state.get('tier',0)<2:
     pick=public_pick(dossier)
     if pick:
      state['topics'].append(pick);state['research']['public-pick']={'sources':[]}
      state.update(tier=2,stage='shortlisted',shortlist={'selected_topic_ids':['public-pick'],'reason':'public_fallback'});save(statepath,state);return RETRY
    state.update(stage='no_candidates',reason='all_candidate_tiers_exhausted');save(statepath,state)
    save(root/('skip-'+date+'.json'),{'date':date,'reason':'적격 이야기 후보 없음','state_id':date})
    return 2
   selection_system='신문 데스크로서 새로운 구체적 이야기나 반복된 사용자 궁금증을 고른다. 공식 자료로 답할 수 있는 반복 질문을 우선 고려한다. 유명 제품이나 양이 많다는 이유만으로 고르지 않는다. 이전 기사와 다른 각도를 찾는다. JSON만: {"selected_topic_ids":[최대2개 topic_id],"reason":str}. 적격 후보가 약하면 줄일 수 있다.'
   selection_input=json.dumps({'candidates':choices,'previous_titles':[r['issue']for r in dossier['history']]},ensure_ascii=False)
   decision=parse(openrouter.complete(selection_system,selection_input,timeout=120,retries=2,max_tokens=1000,allow_external=True))
   chosen=decision.get('selected_topic_ids')
   if not isinstance(chosen,list)or len(chosen)>2 or len(set(chosen))!=len(chosen)or any(key not in eligible for key in chosen):raise ValueError('invalid desk shortlist')
   state.update(stage='shortlisted',shortlist=decision);save(statepath,state)
  if state['stage']=='shortlisted':
   selected=state['shortlist']['selected_topic_ids']
   pool={row['evidence_id']:row for row in dossier['evidence']}
   candidate_rows=[]
   for topic in state['topics']:
    if topic['topic_id']not in selected:continue
    observations=candidate_sample(topic,pool,opts['maximum_candidate_fragments'])
    candidate_rows.extend({k:pool[o['evidence_id']].get(k) for k in ('evidence_id','text','source','sources','date','private','already_published')}for o in observations[:opts['maximum_candidate_fragments']])
   if not candidate_rows:
    state.update(stage='no_candidates',reason='no_supported_new_candidate');save(statepath,state)
    save(root/('skip-'+date+'.json'),{'date':date,'reason':'적격 이야기 후보 없음','state_id':date})
    return 2
   # Compact history covers all prior topics while source texts remain private.
   history=[str(r.get('date'))+' | '+str(r.get('issue'))for r in dossier['history']]
   research=[{'url':r['url'],'text':r['text'][:1500]}for key in selected for r in state['research'][key]['sources'][:2]]
   prompt={'coverage':{k:dossier['coverage'].get(k)for k in ('complete','scope','missing_checkpoint_dates')},'candidate_groups':selected,'evidence':candidate_rows,'research':research,
     'previous_publications':history,'new_story_history':dossier['story_history']}
   aliases={f'E{i+1}':row['evidence_id']for i,row in enumerate(candidate_rows)}
   reverse={value:key for key,value in aliases.items()}
   research_aliases={f'F{i+1}':row for i,row in enumerate(research)}
   model_prompt=copy.deepcopy(prompt)
   for row in model_prompt['evidence']:row['evidence_id']=reverse[row['evidence_id']]
   model_prompt['research']=[{'research_id':key,'text':value['text']}for key,value in research_aliases.items()]
   instruction=MODEL_EDITOR_SYSTEM+'''\n한국어만 사용. 각 기사는 하나의 구체 사건 또는 질문에 한정한다. 같은 서비스라는 이유로 보안 사건과 클라우드 도입처럼 무관한 이야기를 합치지 마라. 각 기사에 짧고 본문을 그대로 복사하지 않는 dek와 article_kind(explainer 또는 experience)를 넣는다. voices에 상황과 진행·결과를 개조식으로 연결하고 timeline은 빈 배열로 둔다. 중복 섹션을 만들지 않는다.
참조 ID는 주어진 evidence_id 그대로. sources에 없는 개인 신원 쓰지 말고 익명 출처명을 유지한다.
근거 ID는 E1, E2 등 짧은 표식을 그대로 복사한다. background에는 research_id(F1 등)를 넣고 해당 원문만 요약한다. URL이나 원문 인용을 생성하지 않는다. 시스템이 정확한 원문 URL을 연결한다.
사용자 질문이 반복되면 공식 근거로 답을 보완한 해설을 쓸 수 있다. 질문을 실제 사용 결과처럼 쓰지 마라.
이미 발행된 사건을 제목만 바꿔 다시 쓰지 마라. 새로운 질문/관찰이 있는 경우만 기사로 낸다. 최대 두 편, 약한 후보는 제외한다.'''
   user_input=json.dumps(model_prompt,ensure_ascii=False)
   if len(instruction)+len(user_input)>16000:raise ValueError('private candidate batch exceeds local budget; split before generation')
   report=approved_report if approved_report is not None else parse(openrouter.complete(instruction,user_input,timeout=120,retries=2,max_tokens=4500,allow_external=True))
   report=restore_refs(report,aliases,research_aliases)
   state.update(stage='drafted',report=report,prompt=prompt,evidence_aliases=aliases,research_aliases=research_aliases);save(statepath,state)
  if state['stage']in ('drafted','repair_pending'):
   research=[r for result in state['research'].values()for r in result['sources']]
   history=[r['story_id']for r in dossier['story_history']if r['date']!=date]
   if state['stage']=='drafted':
    try:check_draft(state['report'],dossier,research,history)
    except ValueError as error:
     if state.get('repair_used'):
      state.update(stage='review_required',gate_error=str(error));save(statepath,state);raise
     cited={eid for i in state['report'].get('items',[])for eid in i.get('evidence_ids',[])}
     repair_input={'candidate':state['report'],'feedback':str(error),
       'evidence':state['prompt']['evidence'],
       'official_sources':state['prompt']['research'],
       'allowed_related_urls':[r.get('url')for r in dossier['evidence']if r['evidence_id']in cited and r.get('url')]}
     repair_input=copy.deepcopy(repair_input)
     reverse={value:key for key,value in state.get('evidence_aliases',{}).items()}
     for row in repair_input['evidence']:row['evidence_id']=reverse.get(row['evidence_id'],row['evidence_id'])
     for item in repair_input['candidate'].get('items',[]):
      for row in [item,*item.get('voices',[]),*item.get('timeline',[])]:
       if 'evidence_ids'in row:row['evidence_ids']=[reverse.get(ref,ref)for ref in row['evidence_ids']]
      for fact in item.get('background',[]):
       for key,source in state.get('research_aliases',{}).items():
        if fact.get('url')==source['url']:fact['research_id']=key;break
       fact.pop('url',None);fact.pop('source_excerpt',None)
     repair_input['official_sources']=[{'research_id':key,'text':source['text']}for key,source in state.get('research_aliases',{}).items()]
     repair_text=json.dumps(repair_input,ensure_ascii=False)
     if len(EDITOR_SYSTEM)+len(repair_text)>15000:raise ValueError('correction exceeds local budget; preserve for desk review')
     state.update(stage='repair_pending',repair_used=True,repair_input=repair_input,gate_error=str(error));save(statepath,state)
   if state['stage']=='repair_pending':
    instruction=MODEL_EDITOR_SYSTEM+'\n기존 후보를 한 번 교정한다. 허용되지 않은 URL과 사실은 삭제한다. 공식 원문에 없는 source_excerpt를 만들지 말고 background를 줄여라. 확인된 사용자 경험은 출처에 귀속시켜 직접 설명한다. 근거가 부족하면 items=[]로 낸다. 새로운 내용으로 바꿔 재생성하지 않는다.'
    fixed=parse(openrouter.complete(instruction,json.dumps(state['repair_input'],ensure_ascii=False),timeout=120,retries=2,max_tokens=4500,allow_external=True))
    fixed=restore_refs(fixed,state.get('evidence_aliases',{}),state.get('research_aliases',{}))
    state.update(stage='drafted',report=fixed);save(statepath,state)
    try:check_draft(fixed,dossier,research,history)
    except ValueError as error:
     state.update(stage='review_required',gate_error=str(error));save(statepath,state);raise
   report=state['report']
   if not report['items']and len(state.get('rejected_candidates',[]))<3:
    state.setdefault('rejected_candidates',[]).append({'shortlist':state.get('shortlist'),'reason':'desk_returned_no_supported_article'})
    state.setdefault('excluded_topics',[]).extend(state.get('shortlist',{}).get('selected_topic_ids',[]))
    for key in ('report','repair_used','repair_input','review','gate_error','shortlist'):state.pop(key,None)
    state.update(stage='researched');save(statepath,state);return RETRY
   if not report['items']:
    state.update(stage='no_candidates',reason='desk_returned_no_supported_article');save(statepath,state)
    save(root/('skip-'+date+'.json'),{'date':date,'reason':'근거를 충족한 기사 없음','state_id':date})
    return 2
   cited={eid for item in report['items']for eid in item['evidence_ids']}
   audit=review_packet(report,state['prompt'])
   audit_input=json.dumps(audit,ensure_ascii=False)
   if len(REVIEW_SYSTEM)+len(audit_input)>16000:raise ValueError('private review exceeds local budget; preserve candidate for split review')
   review=parse(openrouter.complete(REVIEW_SYSTEM,audit_input,timeout=120,retries=2,max_tokens=2000,allow_external=True))
   state['review']=review
   state['review_status']='blocking'if _ai_judge_enabled()else 'advisory'
   if review.get('not_duplicate')is not True:
    state.update(stage='novelty_review_required');save(statepath,state);raise ValueError('novelty is not confirmed; candidate preserved for desk review')
   if review.get('supported')is not True:
    state.update(stage='support_review_required');save(statepath,state);raise ValueError('factual support is not confirmed; candidate preserved for desk review')
   if _ai_judge_enabled()and any(review.get(k)is not True for k in ('ok','supported','privacy','not_duplicate')):
    state.update(stage='review_required');save(statepath,state);raise ValueError('editorial review rejected candidate; preserved for revision')
   state.update(stage='reviewed');save(statepath,state)
  if state['stage']in ('review_required','review_exhausted','novelty_review_required','support_review_required'):raise ValueError('editorial review requires revision; rejected work preserved')
  if state['stage']=='no_candidates':return 2
  if state['stage']=='reviewed':
   if not state['report']['items']:
    state.update(stage='no_candidates');save(statepath,state);return 2
   materialize(state['report'],date,root,args.docs_root,state_id=date)
   state.update(stage='complete');save(statepath,state)
  return 0

def run_until_settled(args,limit=8):
 """Re-enter run() while it asks for the next candidate or coverage tier; the frozen state advances each time."""
 code=run(args)
 for _ in range(limit):
  if code!=RETRY:break
  args=copy.copy(args);args.reviewed_report=None
  code=run(args)
 return 1 if code==RETRY else code
