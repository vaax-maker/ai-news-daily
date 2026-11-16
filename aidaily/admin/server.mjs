/** AI Daily administrative mount. Shared host router owns authentication/origin checks.
 * No listener is opened; existing xbot operator actions remain a compatibility backend.
 */
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {adminThemeCss,adminHeader} from './admin-theme.mjs';
import {glossaryPanel} from './glossary-ui.mjs';
import {readGlossary,saveGlossary} from './glossary-store.mjs';
import {engagementHandler} from './engagement-api.mjs?admin-engagement-v3';
import {engagementLinks} from './engagement-ui.mjs?admin-engagement-v3';

const home=os.homedir();
export function allowedAction(method, route) {
 const fixed={
  '/aidaily/settings':'GET', '/aidaily/source/save':'POST', '/aidaily/source/toggle':'POST',
  '/aidaily/source/archive':'POST', '/aidaily/policies/save':'POST',
  '/briefing/channel/resolve':'POST', '/briefing/channel/add':'POST', '/briefing/channel/delete':'POST',
  '/briefing/channel/toggle':'POST', '/briefing/channel/keywords':'POST', '/briefing/settings':'POST',
  '/briefing/publish-url':'POST', '/briefing/articles/list':'POST',
  '/briefing/articles/remove':'POST', '/briefing/articles/move':'POST',
 };
 return fixed[route]===method || (method==='GET' && /^\/briefing\/(?:publish-status|articles\/republish-status)\/[A-Za-z0-9_-]+$/.test(route));
}
export function renderAdmin(source) {
 const style=source.match(/<style>[\s\S]*?<\/style>/i)?.[0];
 const sections=['p-brief','p-articles'].map(id=>source.match(new RegExp('<section\\b[^>]*id="'+id+'"[^>]*>[\\s\\S]*?<\\/section>','i'))?.[0]);
 if(!style || sections.some(s=>!s)) throw Error('admin_sections_missing');
 let content=sections.join('\n').replace(/(['"])\/(aidaily|briefing)\//g,'$1/aidaily/api/$2/');
 const legacyImageSources=[...content.matchAll(/<input\b[^>]*class="adp-ai-source"[^>]*>/g)].filter(m=>/\bchecked\b/.test(m[0])).map(m=>m[0].match(/value="([^"]*)"/)?.[1]).filter(Boolean);
 content=content.replace(/<div>\s*<strong[^>]*>오늘의 AI 소식 이미지<\/strong>[\s\S]*?<\/div>\s*<div>\s*(?=<strong[^>]*>오늘의 시황 이미지)/,'<div>');
 content=content.replace(/<th>뉴스 이미지<\/th>/g,'');
 content=content.replace(/<td[^>]*>\s*<input\b[^>]*class="ads-ig"[^>]*>\s*<\/td>/g,tag=>'<!-- legacy image candidate '+(/\bchecked\b/.test(tag)?'true':'false')+' -->');
 content=content.replaceAll('colspan="7"','colspan="6"');
 content=content.replace(/(<input\b[^>]*class="ads-limit"[^>]*\bmax=")2(")/g,(_,before,after)=>before+'100'+after);
 content=content.replace("infographic_candidate:row.querySelector('.ads-ig').checked","infographic_candidate:row.innerHTML.indexOf('legacy image candidate true')>=0");
 content=content.replace('<h3 style="margin:18px 0 8px;font-size:15px;">소스 관리</h3>','<h3 style="margin:18px 0 8px;font-size:15px;">소스 관리</h3><p class="subtitle">우선순위: 숫자가 작을수록 먼저 수집합니다. 기사 수는 소스별로 저장한 최대 N건을 적용합니다. aiofmodu는 발행일 전부를 선택할 수 있습니다.</p>');
 content=content.replace('인포그래픽·시황 설정','시황 설정');
 content=content.replace(/var payload=\{ai_infographic_enabled:[\s\S]*?market_enabled:/,'var payload={ai_infographic_enabled:false, ai_infographic_sources:'+JSON.stringify(legacyImageSources)+', market_enabled:');
 content=content.replaceAll('xbot.admin.tab','aidaily.admin.tab');
 content=content.replace('어드민 로그인(Basic Auth)으로만 보호되며','abot 관리자 로그인으로 보호되며');
 return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Daily 관리자</title>'+style+
 '<style>'+adminThemeCss+`.panel{display:block!important;min-width:0}.panel .card{min-width:0;max-width:100%;overflow-x:auto}.admin-home{--bg:#f1f4f2;--surface:#fff;--surface-2:#fafcfb;--ink:#20382c;--muted:#607468;--line:#d9e3dc;--line-soft:#edf0ed;--accent:#1a7046;--accent-ink:#17623e;--accent-wash:#eaf5ee;--radius:6px;--display:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--body:var(--display);max-width:none;padding:0;margin:0;font-family:var(--body)}.admin-home main{margin:auto;max-width:1760px;padding:14px 18px 24px}.admin-home .heading{margin-bottom:12px}.admin-home .card{padding:12px;border-radius:6px}.admin-home .grid{gap:10px}.admin-home h2{font-size:14px}.admin-home h3{font-size:12px;letter-spacing:0;text-transform:none}.admin-home button{background:#1a7046;color:white;border:1px solid #1a7046;border-radius:4px;font-family:inherit}.admin-home input,.admin-home select,.admin-home textarea{border:1px solid #cfdbd3;border-radius:4px;color:#243e2e;background:#fff;font:inherit;max-width:100%}.admin-home th{background:#f3f7f4;color:#5c7564;letter-spacing:0;font-family:inherit}.admin-home th,.admin-home td{padding:6px 9px}.admin-home section{scroll-margin-top:100px}.admin-home .admin-sections{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 12px;font-size:12px}@media(max-width:600px){.admin-home main{padding:10px 12px}.admin-home input,.admin-home select,.admin-home textarea{font-size:16px!important}.admin-home .card{padding:10px!important}}`+'</style></head><body class="admin-home">'+adminHeader('home')+'<main><div class="heading"><h1>AI Daily 관리자</h1></div><nav class="admin-sections"><a href="#p-brief">소스·정책·YouTube</a><a href="#p-glossary">단어장</a><a href="#p-articles">발행 기사</a></nav>'+content+glossaryPanel()+'</main></body></html>';
}
function configuration(){
 const file=process.env.ABOT_SERVICES_FILE || path.join(home,process.platform==='darwin'?'Library/Application Support/abot/services.json':'_abot/services.json');
 const service=JSON.parse(fs.readFileSync(file,'utf8')).services['xbot-admin'];
 if(service.host!=='mini1'||!Number.isInteger(service.local_port))throw Error('backend_config_invalid');
 return service;
}
let authCache={value:null,at:0};
async function credentials(){
 if(authCache.value && Date.now()-authCache.at<5000)return authCache.value;
 const files=[path.join(home,'abot-admin-access/xbot-backend.json'),path.join(home,'.abot-admin-auth.json')];
 for(const file of files){
  if(!fs.existsSync(file))continue;
  const a=JSON.parse(fs.readFileSync(file,'utf8'));if(!a.user||!a.pass)continue;
  const value='Basic '+Buffer.from(a.user+':'+a.pass).toString('base64');
  const status=await new Promise((resolve,reject)=>{const r=http.get({hostname:'127.0.0.1',port:configuration().local_port,path:'/',headers:{authorization:value},timeout:8000},up=>{up.resume();resolve(up.statusCode);});r.on('error',reject);r.on('timeout',()=>r.destroy(Error('timeout')));});
  if(status===200){authCache={value,at:Date.now()};return value;}
  if(status!==401)throw Error('backend_unavailable');
 }
 throw Error('backend_auth_unavailable');
}
export function migrateXbotHtml(html,aidailyUrl='/aidaily/'){
 html=html.replace(/<input\b[^>]*id="t-aidaily"[^>]*>/i,'');
 html=html.replace(/<label\b[^>]*for="t-aidaily"[^>]*>[\s\S]*?<\/label>/i,'');
 html=html.replace(/<section\b[^>]*id="p-brief"[^>]*>[\s\S]*?<\/section>/i,'');
 return html.replace(/<section\b[^>]*id="p-articles"[^>]*>[\s\S]*?<\/section>/i,'');
}
function fail(res,status,error){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify({ok:false,error}));}
function backend(route,method,auth,headers={}){
 return http.request({hostname:'127.0.0.1',port:configuration().local_port,path:route,method,headers:{...headers,authorization:auth},timeout:60000});
}
export const server=http.createServer(async(req,res)=>{
 try{
  const u=new URL(req.url,'http://localhost');
  if(await engagementHandler(req,res))return;
  if(u.pathname==='/api/glossary'){
   if(req.method==='GET'){res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(readGlossary()));return;}
   if(req.method!=='POST')return fail(res,405,'method_not_allowed');
   if(!/^application\/json(?:;|$)/i.test(req.headers['content-type']||''))return fail(res,415,'json_required');
   try{let parts=[],size=0;for await(const part of req){size+=part.length;if(size>262144)return fail(res,413,'too_large');parts.push(part);}let payload;try{payload=JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{return fail(res,400,'invalid_json');}const result=saveGlossary(payload);res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(result));}catch(e){fail(res,e.status||503,e.status?e.message:'dictionary_unavailable');}return;
  }
  if(u.pathname==='/'||u.pathname==='/index.html'){
   if(!['GET','HEAD'].includes(req.method))return fail(res,405,'method_not_allowed');
   const b=backend('/','GET',await credentials());
   b.on('response',up=>{let parts=[],size=0;up.on('data',part=>{size+=part.length;if(size>5000000)b.destroy(Error('oversize'));else parts.push(part);});up.on('end',()=>{try{if(up.statusCode!==200)throw Error('backend_unavailable');const html=renderAdmin(Buffer.concat(parts).toString());res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'});res.end(req.method==='HEAD'?'':html);}catch{fail(res,503,'admin_unavailable');}});});
   b.on('timeout',()=>b.destroy(Error('timeout')));b.on('error',()=>{if(!res.headersSent)fail(res,503,'backend_unavailable');});b.end();return;
  }
  const action=u.pathname.startsWith('/api/')?u.pathname.slice(4):'';
  if(!allowedAction(req.method,action))return fail(res,404,'not_found');
  const headers={};for(const name of ['content-type','content-length','accept'])if(req.headers[name])headers[name]=req.headers[name];
  const b=backend(action+u.search,req.method,await credentials(),headers);
  b.on('response',up=>{res.writeHead(up.statusCode,{'Content-Type':up.headers['content-type']||'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});up.pipe(res);});
  b.on('timeout',()=>b.destroy(Error('timeout')));b.on('error',()=>{if(!res.headersSent)fail(res,503,'backend_unavailable');else res.destroy();});req.pipe(b);
 }catch{if(!res.headersSent)fail(res,503,'admin_unavailable');else res.destroy();}
});
