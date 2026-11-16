"""Confirm the exact V2 edition on the public list and article before marking history."""
import datetime as dt
import hashlib
import html
import json
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit,urlunsplit
from aidaily import config
from aidaily.customer_stories.story_render import story_anchor

class _Item(HTMLParser):
 def __init__(self,target):super().__init__(convert_charrefs=True);self.target=target;self.depth=0;self.text=[];self.links=[];self.found=False
 def handle_starttag(self,tag,attrs):
  values=dict(attrs)
  if not self.depth and values.get('id')==self.target:self.depth=1;self.found=True
  elif self.depth and tag not in ('br','img','input','meta','link','hr','source','wbr'):self.depth+=1
  if self.depth and tag=='a':self.links.append(values.get('href'))
 def handle_endtag(self,tag):
  if self.depth and tag not in ('br','img','input','meta','link','hr','source','wbr'):self.depth-=1
 def handle_data(self,data):
  if self.depth:self.text.append(data)

def section(page,identity):
 parser=_Item(identity);parser.feed(page)
 return parser.found,' '.join(' '.join(parser.text).split()),parser.links


def verify_customer_publication(date, *, attempts=24,delay=10,opener=None):
 path=config.DATA_ROOT/'customer_stories'/(date+'.json')
 if not path.exists():return {'status':'not_generated'}
 report=json.loads(path.read_text()).get('gen')or{}
 if report.get('schema_version')!=2:return {'status':'legacy'}
 rows=json.loads((config.DOCS_ROOT/'search-index.json').read_text())
 expected=[r for r in rows if r.get('date')==date and r.get('kind')=='customer_story']
 ids={i['story_id']for i in report['items']}
 if not ids or {r.get('story_id')for r in expected}!=ids:raise RuntimeError('Current newsroom edition missing from local publication index')
 opener=opener or urllib.request.urlopen
 token=hashlib.sha256(path.read_bytes()).hexdigest()[:12]
 def get(url):
  with opener(url,timeout=30)as response:
   if response.status!=200:raise RuntimeError('Public article/list HTTP failure')
   return response.read().decode('utf-8')
 last=None
 for attempt in range(attempts):
  try:
   listing=get(config.TECH_DAILY_URL+'?date='+date+'&edition='+token)
   for row in expected:
    found,text,links=section(listing,'item-'+str(row['id']))
    if not found or row['title']not in text:raise RuntimeError('Exact newsroom item/title absent from rendered main list')
    content=row.get('story_content')
    if not isinstance(content,dict):raise RuntimeError('Complete newsroom content missing from local publication index')
    required=(['확인된 사실']if content.get('background')else[])+(['사용자 목소리']if content.get('voices')else[])  # headings render only with their section
    for field in ('background','voices','timeline'):
     required.extend(str(part['text'])for part in content.get(field,[])if part.get('text'))
    if content.get('commentary'):required.extend(['기자의 짚어보기',content['commentary']])
    if any(' '.join(value.split())not in text for value in required):raise RuntimeError('Complete current article content absent from public main list')
    for field in ('background','related_links'):
     if any(part.get('url')and part['url']not in links for part in content.get(field,[])):raise RuntimeError('Public main article source link missing')
    if any('/v2/uservoice/'in str(link)for link in links)or '기사 읽기'in text:raise RuntimeError('Main article still sends readers to a detail page')
   ledger=config.DATA_ROOT/'customer_stories/newsroom/story-history.json'
   if ledger.exists():
    from aidaily.customer_stories.newsroom import save
    history=json.loads(ledger.read_text())
    for row in history:
     if row.get('date')==date and row.get('story_id')in ids:row.update(status='published',verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
    save(ledger,history)
   return {'status':'verified','date':date,'story_ids':sorted(ids),'main_list':True,'complete_article_on_main':True}
  except (OSError,ValueError,RuntimeError)as error:last=error
  if attempt+1<attempts:time.sleep(delay)
 raise RuntimeError('Current newsroom public edition not confirmed: '+str(last))
