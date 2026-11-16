import {catalog,listScraps,setScrap,stats} from './engagement-store.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const json=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(value));};
async function body(req){
 if(!/^application\/json(?:;|$)/i.test(req.headers['content-type']||''))throw Object.assign(Error('json_required'),{status:415});
 let value='',size=0;for await(const part of req){size+=part.length;if(size>16384)throw Object.assign(Error('too_large'),{status:413});value+=part;}
 try{return JSON.parse(value);}catch{throw Object.assign(Error('invalid_json'),{status:400});}
}
export async function engagementHandler(req,res,options={}){
 const u=new URL(req.url,'http://localhost'),page=u.pathname.replace(/^\//,'').replace(/\/$/,'');
 if(['analytics','scraps','reader'].includes(page)){
  if(!['GET','HEAD'].includes(req.method)){json(res,405,{error:'method_not_allowed'});return true;}
  const uiURL=new URL('./engagement-ui.mjs',import.meta.url);
  const {engagementPage}=await import(uiURL.href+'?ui='+fs.statSync(uiURL).mtimeMs);
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'});
  res.end(req.method==='HEAD'?'':engagementPage(page));return true;
 }
 if(!u.pathname.startsWith('/api/engagement/'))return false;
 try{
  const action=u.pathname.slice('/api/engagement/'.length);
  if(action==='catalog'&&req.method==='GET'){
   const all=catalog(options),dates=[...new Set(all.map(r=>r.date))].sort().reverse();
   const date=u.searchParams.get('date')||dates[0]||new Date().toISOString().slice(0,10);
   if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||Number.isNaN(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date)throw Object.assign(Error('invalid_date'),{status:400});
   const saved=listScraps({},options),selected=new Set(saved.map(r=>r.uid)),uid=u.searchParams.get('uid');
   let rows=all.filter(r=>r.date===date);
   const kind=u.searchParams.get('page')||'all';
   if(kind!=='all'&&!['tech','econ'].includes(kind))throw Object.assign(Error('invalid_page'),{status:400});
   if(kind!=='all')rows=rows.filter(r=>new URL(r.landing_url).pathname.includes(kind==='econ'?'%EA%B2%BD%EC%A0%9C':'%EA%B8%B0%EC%88%A0')||decodeURIComponent(new URL(r.landing_url).pathname).includes(kind==='econ'?'경제':'기술'));
   if(uid&&!rows.some(r=>r.uid===uid)){
    const snapshot=saved.find(r=>r.uid===uid);
    if(snapshot)rows=[{...snapshot,snapshot_only:!all.some(r=>r.uid===uid)},...rows.filter(r=>r.uid!==uid)];
   }
   const order={ai_news:0,youtube_summary:1,customer_story:2};
   rows.sort((a,b)=>(order[a.kind]??3)-(order[b.kind]??3));
   json(res,200,{date,dates,rows:rows.map(r=>({...r,selected:selected.has(r.uid)}))});return true;
  }
  if(action==='scraps'&&req.method==='GET'){
   const all=listScraps({},options),items=listScraps({q:u.searchParams.get('q')||'',source:u.searchParams.get('source')||''},options);
   json(res,200,{items,sources:[...new Set(all.map(r=>r.source))],total:all.length});return true;
  }
  if(action==='scraps'&&req.method==='POST'){
   if(req.headers['sec-fetch-site']==='cross-site')throw Object.assign(Error('origin_not_allowed'),{status:403});
   json(res,200,setScrap(await body(req),options));return true;
  }
  if(action==='stats'&&req.method==='GET'){
   let collection={};try{collection=JSON.parse(fs.readFileSync(process.env.ABOT_SERVICES_FILE||path.join(os.homedir(),'Library/Application Support/abot/services.json'),'utf8')).services['aidaily-engagement']||{};}catch{}
   json(res,200,{...stats({period:u.searchParams.get('period')||'day',anchor:u.searchParams.get('anchor')||undefined,page:u.searchParams.get('page')||undefined},options),collection_enabled:collection.enabled===true,started_at:collection.enabled_at||null});return true;
  }
  json(res,405,{error:'method_not_allowed'});return true;
 }catch(error){json(res,error.status||503,{error:error.status?error.message:'engagement_unavailable'});return true;}
}
