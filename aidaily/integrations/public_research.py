"""Bounded public background research. Queries use configured public product names only.

Search hits are discovery links, never fact evidence. Only retrieved official-source
bodies become research inputs. No private messages, people or room labels are sent.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import ipaddress
from urllib.parse import urlsplit, urlencode
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from aidaily.integrations import http, article_reader

# Operator-tunable public-topic registry. Keep personal conversation text out.
CATALOG = {
 'chatgpt-codex-limits': {'name':'ChatGPT Codex usage limits','urls':['https://help.openai.com/en/articles/20001625-understanding-chatgpt-and-codex-usage-limits','https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan'],'hosts':['help.openai.com']},
 'grok-bot': {'name':'Grok Bot','urls':['https://docs.x.ai/grok-bot/overview','https://docs.x.ai/grok-bot/faq'],'hosts':['docs.x.ai','x.ai']},
 'whisper': {'name':'Whisper speech recognition','urls':['https://github.com/openai/whisper/blob/main/README.md','https://huggingface.co/openai/whisper-large-v3/blob/main/README.md'],'hosts':['github.com','huggingface.co','openai.com']},
 'codex': {'name':'OpenAI Codex','urls':['https://help.openai.com/en/articles/20001625-understanding-chatgpt-and-codex-usage-limits','https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan','https://developers.openai.com/codex/'],'hosts':['help.openai.com','developers.openai.com','openai.com']},
 'claude-code': {'name':'Claude Code','urls':['https://code.claude.com/docs/en/overview'],'hosts':['code.claude.com','docs.anthropic.com','www.anthropic.com']},
 'cursor': {'name':'Cursor','urls':['https://cursor.com/docs'],'hosts':['cursor.com']},
 'chatgpt': {'name':'ChatGPT','urls':['https://help.openai.com/en/articles/20001625-understanding-chatgpt-and-codex-usage-limits','https://help.openai.com/en/articles/9260256-chatgpt-capabilities-overview'],'hosts':['help.openai.com','openai.com']},
}

class _Readable(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.main=[];self.body=[]
 def handle_starttag(self,tag,attrs):
  if tag not in ('br','img','meta','link','input','hr','source','wbr'):self.stack.append(tag)
 def handle_endtag(self,tag):
  if tag in self.stack:self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
 def handle_data(self,data):
  if any(tag in self.stack for tag in ('script','style','head','nav','footer')):return
  if data.strip():
   self.body.append(data.strip())
   if 'main'in self.stack or 'article'in self.stack:self.main.append(data.strip())

def fetch_official(url,timeout=20,max_chars=14000):
 retrieval=url
 if url.startswith('https://docs.x.ai/')and not url.endswith('.md'):retrieval=url.rstrip('/')+'.md'
 headers_in={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
 try:raw,headers=http.request_bytes(retrieval,timeout=timeout,headers=headers_in)
 except Exception:
  if retrieval==url:raise
  retrieval=url;raw,headers=http.request_bytes(url,timeout=timeout,headers=headers_in)
 text=raw.decode('utf-8','replace')
 if 'markdown'in str(headers.get('Content-Type',''))or retrieval.endswith('.md'):return text[:max_chars]
 extracted=article_reader.extract_article_text(text,max_chars=max_chars)
 if len(extracted)>=160:return extracted
 parser=_Readable();parser.feed(text)
 return '\n'.join(parser.main or parser.body)[:max_chars]

def allowed_url(url, hosts):
 try:
  p=urlsplit(url)
  if p.scheme!='https' or p.username or p.password or not p.hostname or any(ord(c)<33 for c in url):return False
  if p.hostname not in hosts:return False
  p.port
  try:ipaddress.ip_address(p.hostname);return False
  except ValueError:pass
  return True
 except (ValueError,TypeError):return False

def research(service, *, search=True, fetcher=None, searcher=None):
 """Return fetch receipts, official text and explicit omissions; never infer truth."""
 row=CATALOG.get(service)
 if not row:return {'service':service,'status':'unconfigured','sources':[],'errors':[]}
 urls=list(row['urls']);errors=[];hits=0
 if search:
  query=row['name']+' official documentation'
  try:
   raw=(searcher or http.request_bytes)('https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'}),timeout=15)[0]
   for item in ET.fromstring(raw).findall('.//item'):
    url=item.findtext('link') or ''
    if service=='grok-bot'and not any(token in urlsplit(url).path.lower()for token in ('grok-bot','/bot')):continue
    if allowed_url(url,row['hosts']) and url not in urls:urls.append(url);hits+=1
  except Exception as error:errors.append({'stage':'search','error_type':type(error).__name__})
 sources=[];fetcher=fetcher or fetch_official
 for url in urls[:3]:
  if not allowed_url(url,row['hosts']):continue
  if urlsplit(url).hostname in ('github.com','huggingface.co') and not urlsplit(url).path.startswith('/openai/'):continue
  try:
   body=fetcher(url,timeout=20,max_chars=14000)
   if len(body.strip())<160:raise ValueError('insufficient official text')
   sources.append({'url':url,'text':body,'sha256':hashlib.sha256(body.encode()).hexdigest(),
                   'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'primary':True,'verified':True,
                   'verification':'official_url_body_retrieved_not_independent_performance_test'})
  except Exception as error:errors.append({'stage':'fetch','url':url,'error_type':type(error).__name__})
 return {'service':service,'public_query':row['name']+' official documentation' if search else None,
         'search_official_links':hits,'status':'retrieved' if sources else 'unavailable','sources':sources,'errors':errors}
