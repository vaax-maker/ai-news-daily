"""Check the exact pilot edition on the public main page before calling it live."""
import hashlib,json,urllib.request
from aidaily import config
from aidaily.publishing.customer_verification import _Item
from aidaily.publishing.horizon_section import load_editions
class _Horizon(_Item):
 def __init__(self):super().__init__('horizon-briefing');self.attrs={};self.item_ids=[];self.articles={};self.active=None;self.article_depth=None
 def handle_starttag(self,tag,attrs):
  values=dict(attrs)
  if values.get('id')==self.target:self.attrs=values
  super().handle_starttag(tag,attrs)
  if self.depth and tag=='article' and values.get('data-horizon-item'):
   identity=values['data-horizon-item'];self.item_ids.append(identity);self.active=identity;self.article_depth=self.depth
   self.articles[identity]={'text':[],'links':[]}
  if self.active and tag=='a':self.articles[self.active]['links'].append(values.get('href'))
 def handle_data(self,data):
  super().handle_data(data)
  if self.active:self.articles[self.active]['text'].append(data)
 def handle_endtag(self,tag):
  if self.active and tag=='article' and self.depth==self.article_depth:self.active=None;self.article_depth=None
  super().handle_endtag(tag)
def compact(value):return ''.join(str(value).split())
def verify_horizon_publication(date,*,opener=None):
 opener=opener or urllib.request.urlopen
 edition=load_editions().get(date)or{'status':'absent','items':[],'sources':[]}
 token=hashlib.sha256(json.dumps(edition,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]
 url=config.TECH_DAILY_URL+'?date='+date+'&horizon='+token
 with opener(url,timeout=30)as response:
  if response.status!=200:raise RuntimeError('Horizon main HTTPfailure')
  page=response.read().decode('utf-8')
 p=_Horizon();p.feed(page);status=edition['status']
 if not p.found or p.attrs.get('data-horizon-date')!=date or p.attrs.get('data-horizon-status')!=status:raise RuntimeError('Exact Horizon edition state/date absent frommain')
 items=edition.get('items')or[]
 if status not in ('complete','partial'):items=[]
 if sorted(p.item_ids)!=sorted(x['id']for x in items):raise RuntimeError('Exact Horizon currentitems differ')
 text=compact(''.join(p.text))
 for item in items:
  article=p.articles.get(item['id'])or{}
  if item['url']not in article.get('links',[]):raise RuntimeError('Horizon original link missing from matching article')
  article_text=compact(''.join(article.get('text',[])))
  required=[item['title'],item['source_name']]+item['bullets']+([item['reason']]if item.get('reason')else[])
  if item.get('published_at_note'):required.append(item['published_at_note'])
  if any(compact(value)not in article_text for value in required):raise RuntimeError('Complete Horizon explanation/source absent from matching article')
 for source in edition.get('sources',[]):
  if source['url']not in p.links or compact(source['name'])not in text:raise RuntimeError('Horizon collectionsource missing')
 return {'date':date,'status':status,'items':len(items),'collection_sources':len(edition.get('sources')or[]),'url':url,'http_status':200,'exact_edition':True,'edition_sha256':hashlib.sha256(json.dumps(edition,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
