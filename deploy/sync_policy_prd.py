#!/usr/bin/env python3
"""Build a deterministic internal policy PRD; publish only on source change."""
from __future__ import annotations
import argparse, ast, datetime, fcntl, hashlib, html, json, os, plistlib, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOME=Path.home()
STATE=ROOT/'data/policy_prd'
OUTPUT=ROOT/'operations/policy-prd/output'
POLICY=ROOT/'operations/policy-prd/POLICY.md'
MOUNT='/p/aidaily-policy'

def atomic(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+'.new');t.write_text(data);t.replace(p)

def read_json(p,default=None):
    try:return json.loads(p.read_text())
    except (OSError,ValueError):return default

def sources():
    files=set(ROOT.glob('aidaily/**/*.py'))|set(ROOT.glob('deploy/*.sh'))|set(ROOT.glob('deploy/*.py'))|set(ROOT.glob('deploy/*.plist'))
    files|=set(ROOT.glob('deploy/policy-prd-assets/*'))
    files|={POLICY,ROOT/'PRD.md',ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'data/content-settings.json'}
    files|=set(ROOT.glob('operations/*.md'))|set(ROOT.glob('docs/*HANDOFF*.txt'))|{ROOT/'docs/TODO.md'}
    files|=set((HOME/'Library/LaunchAgents').glob('com.aidaily.*.plist'))
    files|={HOME/'Sites/ai-infographic/daybreak-config.json', ROOT/'operations/refresh-schedule-application.json', ROOT/'operations/WORK-ITEMS.json'}
    return sorted(p for p in files if p.is_file() and 'backup' not in str(p).lower())

def manifest():
    return {str(p.relative_to(HOME)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources()}

def render(md):
    import importlib.util
    spec=importlib.util.spec_from_file_location('aidaily_policy_prd_view',Path(__file__).with_name('policy_prd_view.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(md)


def public_settings(raw):
    """Explicit schema allowlist; never mirror arbitrary future secrets."""
    def pick(value, keys):
        return {k:v for k,v in value.items() if k in keys and isinstance(v,(str,int,float,bool,list))} if isinstance(value,dict) else {}
    collection={k:pick(v,{'enabled','since_days','since_hours','default_per_source','hours','min_duration'}) for k,v in raw.get('collection',{}).items() if k in {'ai_news','customer_stories','youtube_summaries','economy_news'}}
    source_fields={'id','name','content_type','connector','enabled','limit_mode','limit','infographic_candidate','priority','include_keywords','exclude_keywords'}
    image_fields={'enabled','article_count','source_ids','story_mix','orientation','background','layout','equal_panels','number_order','read_original_articles','max_article_chars','narrative_mode','weak_link_fallback','max_text_blocks','protagonist_continuity','renderer','format'}
    return {'collection':collection,'sources':[pick(x,source_fields) for x in raw.get('sources',[]) if isinstance(x,dict)],'infographics':{k:pick(v,image_fields) for k,v in raw.get('infographics',{}).items() if k in {'ai_news','market_summary'}},'market_summary':pick(raw.get('market_summary',{}),{'enabled','publish_time','timezone','holiday_policy','indicators'})}

def public_youtube(raw):
    keys={'hours','min_duration','infographic_enabled','infographic_categories','infographic_detail'}
    result={k:v for k,v in raw.items() if k in keys and isinstance(v,(str,int,bool,list))}
    result['channels']=[{k:v for k,v in ch.items() if k in {'handle','category','field','channel_id','title_include'} and isinstance(v,(str,list))} for ch in raw.get('channels',[]) if isinstance(ch,dict)]
    return result

def build(current, previous, semantic_review_required=None):
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    changed=[p for p in sorted(set(current)|set(previous)) if current.get(p)!=previous.get(p)]
    settings=public_settings(read_json(ROOT/'data/content-settings.json',{}))
    youtube=public_youtube(read_json(HOME/'Sites/ai-infographic/daybreak-config.json',{}))
    schedules=[]
    for p in sorted((HOME/'Library/LaunchAgents').glob('com.aidaily.*.plist')):
        d=plistlib.loads(p.read_bytes());label=d.get('Label','');r=subprocess.run(['launchctl','print','gui/'+str(os.getuid())+'/'+label],capture_output=True,text=True)
        descriptors=re.findall(r'"(Hour|Minute|Weekday)" => (\d+)',r.stdout)
        schedules.append({'label':label,'configured':d.get('StartCalendarInterval'),'active_loaded':r.returncode==0,'active_calendar_fields':descriptors})
    deferred={k:v for k,v in read_json(ROOT/'operations/refresh-schedule-application.json',{}).items() if k in {'work_id','status','at'}}
    snapshot={'generated_at':now,'settings':settings,'youtube':youtube,'schedules':schedules,'deferred_schedule':deferred,'source_hashes':current,'changed_files':changed,'semantic_review_required':semantic_review_required if semantic_review_required is not None else any(p.endswith(('.py','.sh')) for p in changed)}
    md=POLICY.read_text()+f'\n\n## 부록 A. 자동 스냅샷\n\n생성 시각: {now}\n\n코드 변경 의미 검토: '+('필요 — 코드·설정 사실은 자동 반영되며 정책 서술의 의미 일치는 담당자가 검토한다.' if snapshot['semantic_review_required'] else '이번 변경에서 코드 변경 감지 없음. 기존 미해결 항목은 본문을 따른다.')+'\n\n'
    md+='### 예약 설정과 실행 상태\n\n| 작업 | 파일 설정 | 활성 예약 값(Hour/Minute/Weekday) |\n|---|---|---|\n'
    for s in schedules:md+='| '+s['label']+' | '+json.dumps(s['configured'],ensure_ascii=False)+' | '+json.dumps(s['active_calendar_fields'])+' |\n'
    md+='\n예약 지연 적용 상태: '+str(deferred.get('status','확인 필요'))+'\n\n### 현재 콘텐츠 설정\n\n```json\n'+json.dumps(settings,ensure_ascii=False,indent=2)+'\n```\n\n### 현재 YouTube 채널·수집 설정\n\n```json\n'+json.dumps(youtube,ensure_ascii=False,indent=2)+'\n```\n'
    md+='\n### 코드에서 추출한 현행 실행 규칙\n\n서술을 자동 추론한 내용이 아니라 현재 함수 원문이다. 정책 변경시 이 부분도 같은 배포에서 갱신한다.\n'
    evidence_functions={
        'aidaily/youtube_summaries/pipeline.py':{'collect_targets'},
        'aidaily/youtube_summaries/processed_state.py':{'state_path','load_processed_ids','record_published'},
        'aidaily/youtube_summaries/resilient_llm.py':{'complete_json'},
        'aidaily/publishing/daily.py':{'run_day'},
        'aidaily/publishing/source_refresh.py':{'main'},
    }
    for relative,names in evidence_functions.items():
        try:
            code=(ROOT/relative).read_text(); tree=ast.parse(code)
        except (OSError,SyntaxError):
            md+='\n정책 함수 추출 확인 필요: '+relative+' (파일 없음 또는 구문 오류)\n'
            continue
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
                md+='\n#### '+relative+' / '+node.name+'\n\n```python\n'+ast.get_source_segment(code,node)+'\n```\n'
    md+='\n## 부록 B. 변경 추적\n\n'
    md+='\n'.join('- '+x for x in changed)+'\n\n소스 SHA256은 policy-snapshot.json에 기록한다. 비밀 환경 파일·원문 대화·런타임 DB는 수집하지 않는다.\n'
    md+='\n## 부록 C. 기존 제품 PRD 및 세부 운영 정책\n\n기존 문서는 작성 당시 기록이다. 현재 기준과 다른 부분은 본문의 정책·자동 스냅샷 및 현재 코드가 우선하며 완료 근거를 확대 해석하지 않는다.\n'
    docs=[ROOT/'PRD.md',ROOT/'docs/TODO.md',ROOT/'AGENTS.md']+sorted(ROOT.glob('operations/YOUTUBE-*.md'))+[ROOT/'operations/SESSION-HANDOFF-20261020.md']
    for p in docs:
        if p.exists():md+='\n### 출처: '+str(p.relative_to(ROOT))+'\n\n'+p.read_text()+'\n'
    import importlib.util
    format_spec=importlib.util.spec_from_file_location('aidaily_policy_prd_format',Path(__file__).with_name('policy_prd_format.py'))
    formatter=importlib.util.module_from_spec(format_spec);format_spec.loader.exec_module(formatter)
    md=formatter.bullet_prose(md)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for asset in (ROOT/'deploy/policy-prd-assets').glob('*'):
        if asset.is_file():atomic(OUTPUT/asset.name,asset.read_text())
    atomic(OUTPUT/'PRD.md',md);atomic(OUTPUT/'index.html',render(md));atomic(OUTPUT/'policy-snapshot.json',json.dumps(snapshot,ensure_ascii=False,indent=2))
    return changed

def publish(state):
    transaction=state.get('pending_transaction')
    if state.get('submission_uncertain') and not transaction:raise RuntimeError('Unknown publication outcome; reconcile existing transaction before another submission')
    cmd=[str(HOME/'.local/bin/abot-web-register')]
    if transaction:cmd+=['--resume',transaction]
    else:cmd+=['aidaily-policy',str(OUTPUT),'--mount',MOUNT,'--type','type1','--drive-session','aidaily']
    state['submission_uncertain']=True
    atomic(STATE/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
    atomic(STATE/'last-publish.log',p.stdout+'\n'+p.stderr)
    result=None
    for line in p.stdout.splitlines():
        try:result=json.loads(line)
        except ValueError:pass
    found=re.search(r'(?:drive|mini1)-[a-f0-9]{24}',p.stdout+' '+p.stderr)
    if found:state['pending_transaction']=found[0]
    if not transaction and not found and any(x in p.stderr for x in ('central_storage_preflight_inconclusive','central_storage_preflight_unavailable','local_preflight_failed')):
        state['submission_uncertain']=False  # Read-only preflight failed before any submission.
    if p.returncode or not result or not result.get('ok'):
        atomic(STATE/'state.json',json.dumps(state,ensure_ascii=False,indent=2));raise RuntimeError('Policy publication incomplete; inspect private last-publish.log, resume same transaction')
    state.update(publication=result,published_digest=state['built_digest'],submission_uncertain=False)
    state.pop('pending_transaction',None)
    atomic(STATE/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--publish',action='store_true');ap.add_argument('--acknowledge-policy-review',action='store_true',help='Explicitly record that code-policy meaning has been reviewed');args=ap.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'sync.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        state=read_json(STATE/'state.json',{})
        if state.get('submission_uncertain') or state.get('pending_transaction'):
            if args.publish:publish(state)
            return
        current=manifest();digest=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
        if digest!=state.get('built_digest') or args.acknowledge_policy_review:
            previous=state.get('manifest',{})
            code_changed=any(p.endswith(('.py','.sh')) and current.get(p)!=previous.get(p) for p in set(current)|set(previous))
            review=(state.get('semantic_review_required',False) or code_changed) and not args.acknowledge_policy_review
            state['semantic_review_required']=review
            changed=build(current,previous,review)
            state.update(built_digest=digest,manifest=current,changed_files=changed)
            if args.acknowledge_policy_review:state.pop('published_digest',None)
            atomic(STATE/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
        if args.publish and state.get('published_digest')!=state.get('built_digest'):publish(state)
        else:print(json.dumps({'status':'unchanged' if state.get('published_digest')==digest else 'built','digest':digest}))

if __name__=='__main__':main()
