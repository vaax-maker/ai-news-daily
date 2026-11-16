import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';

export const defaults={schema:1,revision:0,terms:[
 {id:'seedance',canonical:'Seedance',aliases:['Seed Dance','시댄스','씨댄스','시 댄스','씨 댄스','C댄스','C 댄스'],description:'ByteDance의 영상 생성 모델',source_url:'https://seed.bytedance.com/en/seedance',context:[],enabled:true},
 {id:'openclaw',canonical:'OpenClaw',aliases:['Open Claw','오픈클로','오픈클로우'],description:'오픈소스 AI 어시스턴트',source_url:'https://docs.openclaw.ai/',context:[],enabled:true}
]};
export function glossaryFile(){return process.env.AIDAILY_GLOSSARY_FILE||fileURLToPath(new URL('../../data/terminology/glossary.json',import.meta.url));}
function problem(status,error){return Object.assign(new Error(error),{status});}
export function readGlossary(file=glossaryFile()){
 if(!fs.existsSync(file))return structuredClone(defaults);
 const value=JSON.parse(fs.readFileSync(file,'utf8'));
 if(value.schema!==1||!Number.isInteger(value.revision)||!Array.isArray(value.terms))throw problem(503,'dictionary_unavailable');
 return value;
}
export function validateTerms(terms){
 if(!Array.isArray(terms)||terms.length>500)throw problem(400,'invalid_terms');
 const ids=new Set(),names=new Set(),forms=new Map();
 const str=(v,max)=>{if(typeof v!=='string'||v.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v))throw problem(400,'invalid_field');return v.trim();};
 return terms.map(row=>{
  const id=str(row.id,80),canonical=str(row.canonical,100);
  if(!/^[a-zA-Z0-9_-]+$/.test(id)||ids.has(id)||!canonical)throw problem(400,'invalid_term');
  const key=canonical.toLocaleLowerCase();if(names.has(key))throw problem(400,'duplicate_canonical');
  ids.add(id);names.add(key);
  const list=(v)=>{if(!Array.isArray(v)||v.length>50)throw problem(400,'invalid_field');return [...new Set(v.map(x=>str(x,100)).filter(Boolean))];};
  const aliases=list(row.aliases),context=list(row.context);
  const source_url=str(row.source_url,1000),description=str(row.description,1000);
  if(source_url){let u;try{u=new URL(source_url);}catch{throw problem(400,'invalid_url');}if(!['https:','http:'].includes(u.protocol)||u.username||u.password)throw problem(400,'invalid_url');}
  if(typeof row.enabled!=='boolean')throw problem(400,'invalid_field');
  for(const form of [canonical,...aliases]){const k=form.toLocaleLowerCase();if(forms.has(k)&&forms.get(k)!==id)throw problem(400,'duplicate_alias');forms.set(k,id);}
  return {id,canonical,aliases,description,source_url,context,enabled:row.enabled};
 });
}
export function saveGlossary(payload,file=glossaryFile()){
 if(!Number.isInteger(payload?.revision))throw problem(400,'invalid_revision');
 const terms=validateTerms(payload.terms);
 fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});
 const lock=file+'.lock';try{fs.mkdirSync(lock,{mode:0o700});}catch(e){if(e.code==='EEXIST')throw problem(409,'dictionary_busy');throw e;}
 let tmp;
 try{
  const previous=readGlossary(file);
  if(previous.revision!==payload.revision)throw problem(409,'revision_conflict');
  const next={schema:1,revision:previous.revision+1,terms,updated_at:new Date().toISOString()};
  tmp=file+'.'+randomUUID()+'.new';fs.writeFileSync(tmp,JSON.stringify(next,null,2)+'\n',{mode:0o600});
  fs.renameSync(tmp,file);return next;
 }finally{if(tmp&&fs.existsSync(tmp))fs.unlinkSync(tmp);fs.rmdirSync(lock);}
}
