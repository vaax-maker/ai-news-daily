import { adminThemeCss, adminHeader } from './admin-theme.mjs';
const views = {analytics:'방문 통계',scraps:'스크랩',reader:'소식지 보기'};
export function engagementLinks(){return '<a href="/aidaily/analytics">방문 통계</a> · <a href="/aidaily/scraps">스크랩</a> · <a href="/aidaily/reader">소식지 보기</a>';}
export function engagementPage(view='reader') {
  if (!Object.hasOwn(views,view)) view='reader';
  return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${views[view]} · AI Daily</title><style>${adminThemeCss}
article{position:relative;scroll-margin-top:110px;overflow-wrap:anywhere}article:target,article.focused{outline:2px solid #84b89a}article h3{padding-right:44px}.save{position:absolute;right:5px;top:3px;display:flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;cursor:pointer}.save input{height:18px;min-height:18px;width:18px;padding:0;accent-color:#1a7046}.save:focus-within{outline:2px solid #4b9470;border-radius:4px}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.meta{font-size:11px;color:#607769}.links{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px}.links a{padding:5px 0}.total{font-size:25px;font-weight:700;margin:0;letter-spacing:-.5px}.bars{list-style:none;margin:0;padding:0}.bars li{display:grid;grid-template-columns:80px minmax(0,1fr) 45px;align-items:center;gap:8px;margin:7px 0;font-size:11px}.bar{height:10px;background:#34845a;border-radius:2px;min-width:0}.track{background:#edf3ef;border-radius:2px}.stats-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;align-items:start}.stats-grid>.panel{margin:0}ul{padding-left:18px}#content>section:not(.panel):not(.stats-grid)>h2{margin:14px 0 8px}.panel>h2{padding-bottom:9px;border-bottom:1px solid #e5eae6}@media(max-width:800px){.stats-grid{grid-template-columns:1fr}.panel,article{padding:10px}}
</style>${adminHeader(view)}<main><h1>${views[view]}</h1><div id="controls" class="controls"></div><div id="status" class="status" role="status" aria-live="polite"></div><div id="content" aria-busy="true"></div></main><script>(${client.toString()})(${JSON.stringify(view)});</script></html>`;
}
function client(view){
  const $=id=>document.getElementById(id), controls=$('controls'), content=$('content'),status=$('status');
  const params=new URLSearchParams(location.search); let seq=0; let pageOptions=[];
  function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;}
  function link(text,url){const n=el('a',text);try{const parsed=new URL(url,location.origin);if(!['http:','https:'].includes(parsed.protocol))return el('span',text);n.href=parsed.href;}catch{return el('span',text);}return n;}
  function notice(text){status.replaceChildren(el('span',text));}
  function sync(){const query=new URLSearchParams();for(const [key,value] of Object.entries(state))if(value)query.set(key,value);history.replaceState(null,'',location.pathname+'?'+query.toString()+location.hash);}
  async function api(path,options){const response=await fetch('/aidaily/api/engagement/'+path,{credentials:'same-origin',...options});if(response.status===401){const e=new Error('로그인이 필요합니다.');e.login=true;throw e;}if(!response.ok)throw new Error('요청을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.');return response.json();}
  function error(err,retry){status.replaceChildren(el('span',err.message+' '));if(err.login){status.append(link('로그인','/sites/login?next='+encodeURIComponent(location.pathname+location.search+location.hash)));}else{const b=el('button','다시 시도');b.type='button';b.onclick=retry;status.append(b);}}
  function field(title,type,value,onchange){const label=el('label',title),input=document.createElement('input');input.type=type;input.value=value;input.onchange=()=>onchange(input.value);label.append(input);controls.append(label);return input;}
  function select(title,options,value,onchange){const label=el('label',title),input=document.createElement('select');for(const [v,t]of options){const o=el('option',t);o.value=v;input.append(o);}input.value=value;input.onchange=()=>onchange(input.value);label.append(input);controls.append(label);return input;}
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const state=view==='analytics'?{period:params.get('period')||'day',anchor:params.get('anchor')||today,page:params.get('page')||''}:view==='scraps'?{q:params.get('q')||'',source:params.get('source')||''}:{date:params.get('date')||'',page:params.get('page')||'all',uid:params.get('uid')||''};
  if(view==='analytics'&&!['day','week','month'].includes(state.period))state.period='day';
  if(view==='reader'&&!['tech','econ','all'].includes(state.page))state.page='all';
  const changed=()=>{sync();load();};
  function drawControls(data){controls.replaceChildren();if(view==='analytics'){
    select('기간',[['day','일간'],['week','주간'],['month','월간']],state.period,v=>{state.period=v;changed();});
    field('기준일','date',state.anchor,v=>{state.anchor=v;changed();});
    if(data?.pages?.length)pageOptions=Array.from(new Set([...pageOptions,...data.pages.map(p=>p.page)]));
    if(state.page&&!pageOptions.includes(state.page))pageOptions.push(state.page);
    select('페이지',[['','전체'],...pageOptions.map(p=>[p,p])],state.page,v=>{state.page=v;changed();});
  }else if(view==='reader'){
    const dates=Array.from(new Set([state.date,...(data?.dates||[])].filter(Boolean))).sort().reverse();
    select('발행일',dates.length?dates.map(d=>[d,d]):[['','최신 발행일']],state.date,v=>{state.date=v;state.uid='';changed();});
    select('소식지',[['all','전체'],['tech','기술'],['econ','경제']],state.page,v=>{state.page=v;changed();});
  }else{
    field('제목·내용 검색','search',state.q,v=>{state.q=v;changed();});
    const sources=Array.from(new Set([state.source,...(data?.sources||[])].filter(Boolean)));
    select('출처',[['','전체 출처'],...sources.map(s=>[s,s])],state.source,v=>{state.source=v;changed();});
  }}
  function article(row,scrap=false){const a=el('article');a.id=row.uid;
    const h=el('h3');h.append(scrap?link(row.title,'/aidaily/reader?'+new URLSearchParams({date:row.date||'',uid:row.uid,page:'all'})):el('span',row.title));a.append(h);
    a.append(el('div',[row.date,row.channel||row.source].filter(Boolean).join(' · '),'meta'));
    if(row.snapshot_only)a.append(el('p','현재 발행본에서 제외된 소식입니다. 스크랩 당시 저장된 내용을 표시합니다.','muted'));
    if(row.summary&&!(Array.isArray(row.bullets)&&row.bullets.length))a.append(el('p',row.summary));if(Array.isArray(row.bullets)&&row.bullets.length){const ul=el('ul');row.bullets.forEach(b=>ul.append(el('li',b)));a.append(ul);}
    if(scrap&&row.saved_at)a.append(el('p','스크랩 '+new Date(row.saved_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}),'meta'));
    const links=el('div',undefined,'links');if(row.landing_url)links.append(link('발행 페이지',row.landing_url));if(row.url)links.append(link('원문',row.url));if(links.childNodes.length)a.append(links);
    if(scrap){const remove=el('button','스크랩 해제');remove.type='button';remove.onclick=async()=>{remove.disabled=true;try{await api('scraps',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid:row.uid,selected:false})});notice('스크랩을 해제했습니다.');load();}catch(err){remove.disabled=false;error(err,()=>remove.click());}};a.append(remove);
    }else{const label=el('label',undefined,'save'),input=document.createElement('input');input.type='checkbox';input.checked=Boolean(row.selected);input.setAttribute('aria-label',row.title+' 스크랩');label.append(input,el('span','스크랩','sr'));a.append(label);input.onchange=async()=>{const previous=Boolean(row.selected),desired=input.checked;input.checked=previous;input.disabled=true;try{const result=await api('scraps',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid:row.uid,date:row.date,selected:desired})});row.selected=Boolean(result.selected);input.checked=row.selected;notice(row.selected?'스크랩에 저장했습니다.':'스크랩을 해제했습니다.');}catch(err){input.checked=previous;error(err,()=>{input.checked=desired;input.dispatchEvent(new Event('change'));});}finally{input.disabled=false;}};}
    return a;
  }
  function drawStats(data){if(data.collection_enabled===false){const waiting=el('p','방문 수집 연결 대기 · 아직 일반 독자의 방문을 집계하지 않습니다. 스크랩은 이용할 수 있습니다.','status');waiting.setAttribute('role','status');content.append(waiting);}const panel=el('section',undefined,'panel');panel.setAttribute('aria-label','방문 통계 요약');panel.append(el('p',(data.start||'')+' ~ '+(data.end||''),'muted'),el('p',data.collection_enabled===false?'수집 연결 대기':Number(data.total||0).toLocaleString('ko-KR')+' PV','total'),el('p','페이지 조회 수입니다. 한국 시간 기준이며 주간은 월요일부터 집계합니다.','muted'));content.append(panel);
    const trend=el('section',undefined,'panel');trend.append(el('h2','일별 조회 추이'));const series=data.series||[],max=Math.max(1,...series.map(s=>Number(s.pv)||0));const bars=el('ul',undefined,'bars');for(const s of data.collection_enabled===false?[]:series){const li=el('li');li.setAttribute('aria-label',s.date+' '+s.pv+'회');const track=el('div',undefined,'track'),bar=el('div',undefined,'bar');bar.style.width=(Math.max(0,Number(s.pv)||0)/max*100)+'%';track.append(bar);track.setAttribute('aria-hidden','true');li.append(el('span',s.date),track,el('span',Number(s.pv||0).toLocaleString()));bars.append(li);}trend.append(bars);if(!data.total)trend.append(el('p',data.collection_enabled===false?'수집 연결 후 방문 추이가 표시됩니다.':'선택한 기간에 기록된 방문이 없습니다.','empty'));content.append(trend);
    const section=el('section',undefined,'panel');section.append(el('h2','페이지별 조회'));const table=el('table'),thead=el('thead'),hr=el('tr');for(const t of ['페이지','조회 수']){const th=el('th',t);th.scope='col';hr.append(th);}thead.append(hr);table.append(thead);const body=el('tbody');for(const p of data.pages||[]){const tr=el('tr');tr.append(el('td',p.page),el('td',data.collection_enabled===false?'—':Number(p.pv||0).toLocaleString()));body.append(tr);}table.append(body);section.append(table);const grid=el('div',undefined,'stats-grid');grid.append(trend,section);content.append(grid,el('p',data.started_at?'통계 수집 시작: '+new Date(data.started_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})+' KST · 설치 이전 방문은 포함되지 않습니다.':'통계는 수집 기능 설치 이후부터 기록됩니다.','muted'));
  }
  async function load(){const request=++seq;content.setAttribute('aria-busy','true');notice('불러오는 중…');try{
    const query=new URLSearchParams(state);const data=await api((view==='analytics'?'stats':view==='scraps'?'scraps':'catalog')+'?'+query);if(request!==seq)return;
    if(view==='reader'&&data.date){state.date=data.date;sync();}drawControls(data);content.replaceChildren();status.replaceChildren();
    if(view==='analytics')drawStats(data);else{const rows=view==='scraps'?(data.items||[]).slice().sort((a,b)=>String(b.saved_at).localeCompare(String(a.saved_at))):(data.rows||[]);
      if(!rows.length)content.append(el('p',view==='scraps'?'저장된 스크랩이 없습니다. 소식지 보기에서 관심 소식을 체크해 주세요.':'선택한 날짜에 발행된 소식이 없습니다.','empty'));
      if(view==='scraps')rows.forEach(r=>content.append(article(r,true)));else{const groups=new Map();rows.forEach(r=>{const key=r.source||r.channel||r.kind||'소식';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);});for(const [source,list]of groups){const section=el('section');section.append(el('h2',source));list.forEach(r=>section.append(article(r)));content.append(section);}}
      if(view==='reader'){const target=state.uid||decodeURIComponent(location.hash.slice(1));if(target){const a=document.getElementById(target);if(a){a.classList.add('focused');a.tabIndex=-1;a.focus({preventScroll:true});a.scrollIntoView({behavior:'smooth',block:'start'});}else notice('해당 소식을 찾을 수 없습니다. 스크랩 목록에서 다시 선택해 주세요.');}}
    }
  }catch(err){if(request===seq)error(err,load);}finally{if(request===seq)content.setAttribute('aria-busy','false');}}
  drawControls();load();
}
