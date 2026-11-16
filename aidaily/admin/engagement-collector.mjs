/** Anonymous write-only page-view pixel. Never serves admin data or opens a listener. */
import http from 'node:http';
import crypto from 'node:crypto';
import {recordVisit} from './engagement-store.mjs';
const PIXEL=Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7','base64');
const allowed=new Set(['https://wootom.github.io','https://vaax-maker.github.io']);
const rates=new Map();
export function collectorHandler(req,res,options={}){
 const u=new URL(req.url,'http://localhost');
 const headers={'Cache-Control':'no-store, max-age=0','X-Content-Type-Options':'nosniff','Access-Control-Allow-Origin':'*','Referrer-Policy':'no-referrer'};
 const finish=(status)=>{res.writeHead(status,{...headers,'Content-Type':'image/gif'});res.end(req.method==='HEAD'?'':PIXEL);};
 if(req.method!=='GET'||u.pathname!=='/pixel.gif'){res.writeHead(404,headers);res.end();return;}
 let source;try{source=new URL(req.headers.origin||req.headers.referer||'').origin;}catch{return finish(204);}
 if(!allowed.has(source))return finish(204);
 if(/bot|crawler|spider|preview|headless/i.test(req.headers['user-agent']||''))return finish(204);
 const minute=Math.floor(Date.now()/60000),key=crypto.createHash('sha256').update(`${req.socket?.remoteAddress||''}:${minute}`).digest('hex');
 const count=(rates.get(key)||0)+1;rates.set(key,count);
 if(rates.size>5000)rates.clear();
 if(count>120)return finish(429);
 try{recordVisit({event_id:u.searchParams.get('event_id'),page:u.searchParams.get('page'),date:u.searchParams.get('date')||undefined},options);finish(200);}
 catch{finish(204);}
}
export const server=http.createServer(collectorHandler);
