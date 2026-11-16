import test from 'node:test';
import assert from 'node:assert/strict';
import {allowedAction,renderAdmin,server,migrateXbotHtml} from './server.mjs';
test('administrative backend allowlist excludes unrelated bot mutations',()=>{
 assert(allowedAction('POST','/aidaily/source/save'));assert(allowedAction('GET','/briefing/publish-status/abc-123'));
 for(const p of ['/bot/start','/aidaily/source/save/extra','/briefing/channel/unknown','/briefing/publish-status/../settings'])assert(!allowedAction('POST',p));
 assert(!allowedAction('GET','/aidaily/source/save'));assert(!allowedAction('DELETE','/briefing/articles/remove'));
});
test('mount has no independent listener',()=>{assert.equal(server.listening,false);assert.equal(server.listenerCount('request'),1);});
test('isolates relevant panels and rewrites all action URL strings',()=>{
 const html=renderAdmin('<style>.panel{display:none}</style><section id="p-other">private bot controls</section><section class="panel" id="p-brief"><script>fetch("/aidaily/source/save");fetch(\'/briefing/settings\')</script></section><section class="panel" id="p-articles"><script>fetch(\'/briefing/articles/list\')</script></section>');
 assert(!html.includes('private bot controls'));assert(html.includes('/aidaily/api/aidaily/source/save'));assert(html.includes('/aidaily/api/briefing/settings'));assert(html.includes('lang="ko"'));assert(html.includes('AI Daily 관리자'));
});
test('missing backend sections fail closed',()=>assert.throws(()=>renderAdmin('<style></style><section id="p-brief"></section>')));

test('xbot migration retains other tabs and provides saved-tab exit',()=>{
 const original='<label for="t-aidaily">7) 오늘의 AI 소식</label><section id="p-bot">bot</section><section class="panel" id="p-brief">old controls</section><section class="panel" id="p-articles">old articles</section>';
 const html=migrateXbotHtml(original,'/aidaily/');
 assert(html.includes('id="p-bot">bot'));assert(!html.includes('id="p-brief"'));assert(!html.includes('href="/aidaily/"'));assert(!html.includes('old controls'));assert(!html.includes('old articles'));
});
test('request handler rejects disallowed mutations without contacting backend',async()=>{
 const handler=server.listeners('request')[0];
 let status,body;
 const req={url:'/api/bot/start',method:'POST',headers:{}};
 const res={headersSent:false,writeHead(s){status=s;this.headersSent=true;},end(b){body=b;}};
 await handler(req,res);
 assert.equal(status,404);assert.deepEqual(JSON.parse(body),{ok:false,error:'not_found'});
});
