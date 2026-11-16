"""Verify the exact four-column government table on the public daily page."""
import hashlib,json,urllib.request
from html.parser import HTMLParser
from aidaily import config
from aidaily.publishing.gov_section import load_editions,notice_time,source_display
from aidaily.publishing.customer_verification import _Item
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class _Section(_Item):
 def handle_starttag(self,tag,attrs):
  if tag=='col':return
  super().handle_starttag(tag,attrs)
 def handle_endtag(self,tag):
  if tag=='col':return
  super().handle_endtag(tag)

class _Notices(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.current=None;self.depth=0;self.items={};self.section_depth=0;self.table_depth=0;self.table_count=0;self.headers=[];self.header=None;self.cell=None;self.states=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='section'and attrs.get('id')=='gov-updates':self.section_depth=1;self.states.append(attrs)
  elif self.section_depth and tag not in VOID:self.section_depth+=1
  if not self.section_depth:return
  if tag=='table'and 'gov-table'in attrs.get('class','').split():self.table_depth=1;self.table_count+=1
  elif self.table_depth and tag not in VOID:self.table_depth+=1
  if not self.table_depth:return
  if tag=='th':self.header=[];self.headers.append(self.header)
  if tag=='tr'and attrs.get('data-gov-item'):
   self.current={'cells':[]};self.items.setdefault(attrs['data-gov-item'],[]).append(self.current);self.depth=1
  elif self.depth and tag not in VOID:self.depth+=1
  if self.current is not None and tag=='td':self.cell={'text':[],'links':[]};self.current['cells'].append(self.cell)
  if self.cell is not None and tag=='a':self.cell['links'].append(attrs.get('href'))
 def handle_endtag(self,tag):
  if tag=='td':self.cell=None
  if tag=='th':self.header=None
  if self.depth and tag not in VOID:
   self.depth-=1
   if not self.depth:self.current=None
  if self.table_depth and tag not in VOID:self.table_depth-=1
  if self.section_depth and tag not in VOID:self.section_depth-=1
 def handle_data(self,text):
  if self.cell is not None:self.cell['text'].append(text)
  if self.header is not None:self.header.append(text)

def verify_gov_publication(date,*,opener=None):
 edition=load_editions().get(date)or{'date':date,'status':'absent','items':[],'sources':[]}
 digest=hashlib.sha256(json.dumps(edition,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 url=config.TECH_DAILY_URL+'?date='+date+'&gov='+digest[:12]
 with (opener or urllib.request.urlopen)(url,timeout=30)as response:
  if response.status!=200:raise RuntimeError('Government public HTTP failure')
  page=response.read().decode('utf-8')
 parser=_Section('gov-updates');parser.feed(page)
 p=_Notices();p.feed(page)
 if not parser.found or len(p.states)!=1:raise RuntimeError('Government section missing/duplicate')
 attrs=p.states[0]
 if attrs.get('data-gov-date')!=date or attrs.get('data-gov-status')!=edition['status']:raise RuntimeError('Government date/status differs')
 if p.table_count!=1 or [''.join(x).strip()for x in p.headers]!=['일시','출처','기관명','제목']:raise RuntimeError('Government four-column header differs')
 items=edition.get('items',[])if edition['status']in ('complete','partial')else[]
 if sorted(p.items)!=sorted(row['id']for row in items)or any(len(v)!=1 for v in p.items.values()):raise RuntimeError('Government notice identities differ')
 compact=lambda s:''.join(s.split())
 for row in items:
  cells=p.items[row['id']][0]['cells'];required=[notice_time(row),source_display(row),row.get('agency')or'기관 미확인',row['title']]
  if len(cells)!=4 or any(compact(''.join(cell['text']))!=compact(value)for cell,value in zip(cells,required)):raise RuntimeError('Government table cell differs')
  if cells[3]['links']!=[row['url']]:raise RuntimeError('Government title original link differs')
 for source in edition.get('sources',[]):
  if source['url']not in parser.links or compact(source['name'])not in compact(''.join(parser.text)):raise RuntimeError('Government source missing')
 return {'date':date,'status':edition['status'],'items':len(items),'http_status':200,'url':url,'exact_edition':True,'four_column_table':True,'edition_sha256':digest}
