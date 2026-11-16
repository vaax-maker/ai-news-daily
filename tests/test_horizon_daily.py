"""The optional pilot resumes without blocking the established publication flow."""
import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aidaily import config
from aidaily.publishing import daily
class HorizonDailyTests(unittest.TestCase):
 date='2026-11-03'
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.settings=self.root/'data/ai_news/horizon/settings.json';self.write(self.settings,{'pilot':{'start':self.date,'end':'2026-11-09'}})
  for p,value in [('docs/daily.html','ready'),('docs/archive/index.json',[{'date':self.date,'stories':[{'body_bullets':['ready']}]}]),('docs/v2/uservoice/'+self.date+'.html',self.date),('data/customer_stories/'+self.date+'.json',{'date':self.date,'gen':{'items':[{'title':'ready'}]}}),('docs/search-index.json',[]),('site/index.html','ready')]:self.write(self.root/p,value)
  self.patches=patch.multiple(config,PROJECT_ROOT=self.root,DOCS_ROOT=self.root/'docs',DATA_ROOT=self.root/'data',PUBLISHING_REPOSITORY=self.root/'site');self.patches.start();self.addCleanup(self.patches.stop);self.calls=[]
 def write(self,p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value)if isinstance(value,(dict,list))else value)
 def edition(self):self.write(self.root/'data/ai_news/horizon/editions'/f'{self.date}.json',{'date':self.date,'status':'complete','items':[],'sources':[]})
 def state(self):return json.loads((self.root/'data/publishing/daily_runs'/f'{self.date}.json').read_text())
 def run_day(self,command):
  with patch.object(daily.subprocess,'run',side_effect=command),patch.object(daily,'verify_publication',return_value={'http_status':200}),patch.object(daily,'alert_failure',side_effect=AssertionError('optional experiment must not send failure messages')):daily.run_day(self.date,adopt_generated=True,no_notify=True)
 def test_pending_then_completed_output_republishes_without_hiding_pending(self):
  def command(args,**kw):
   self.calls.append(args[2])
   if args[2]=='aidaily.ai_news.horizon':self.write(self.root/'data/ai_news/horizon/runs'/f'{self.date}.json',{'status':'pending'});return SimpleNamespace(returncode=1)
   return SimpleNamespace(returncode=0)
  self.run_day(command);self.assertEqual(self.state()['stages']['horizon']['status'],'pending');self.assertIn('aidaily.publishing.pipeline',self.calls)
  def complete(args,**kw):
   self.calls.append(args[2])
   if args[2]=='aidaily.ai_news.horizon':self.edition()
   return SimpleNamespace(returncode=0)
  self.run_day(complete);self.assertEqual(self.state()['stages']['horizon']['status'],'complete');self.assertEqual(self.calls.count('aidaily.publishing.pipeline'),2)
 def test_missing_optional_runtime_keeps_existing_publication(self):
  def command(args,**kw):
   self.calls.append(args[2])
   if args[2]=='aidaily.ai_news.horizon':raise FileNotFoundError('isolated runtime unavailable')
   return SimpleNamespace(returncode=0)
  self.run_day(command);self.assertEqual(self.state()['status'],'published_unnotified');self.assertEqual(self.state()['stages']['horizon']['status'],'failed');self.assertIn('aidaily.publishing.pipeline',self.calls)
 def test_completed_cached_edition_does_not_submit_again(self):
  self.edition()
  def command(args,**kw):self.calls.append(args[2]);return SimpleNamespace(returncode=0)
  self.run_day(command);self.assertNotIn('aidaily.ai_news.horizon',self.calls)
 def test_zero_exit_without_an_edition_is_not_success(self):
  self.run_day(lambda *a,**kw:SimpleNamespace(returncode=0));self.assertEqual(self.state()['stages']['horizon']['status'],'failed')
 def test_optional_timeout_preserves_pending_and_existing_publication(self):
  def command(args,**kw):
   self.calls.append(args[2])
   if args[2]=='aidaily.ai_news.horizon':
    self.assertEqual(kw['timeout'],120)
    self.write(self.root/'data/ai_news/horizon/runs'/f'{self.date}.json',{'status':'enriching','current':{'item_id':'frozen'}})
    raise subprocess.TimeoutExpired(args,120)
   return SimpleNamespace(returncode=0)
  self.run_day(command);self.assertEqual(self.state()['stages']['horizon']['status'],'pending');self.assertIn('aidaily.publishing.pipeline',self.calls)
 def test_seven_day_window_stops_new_requests(self):
  self.write(self.settings,{'pilot':{'start':'2026-10-20','end':'2026-10-26'}})
  def command(args,**kw):self.calls.append(args[2]);return SimpleNamespace(returncode=0)
  self.run_day(command);self.assertNotIn('aidaily.ai_news.horizon',self.calls);self.assertNotIn('horizon',self.state()['stages'])

class HorizonHistoryTests(unittest.TestCase):
 def test_only_verified_edition_enters_history_and_same_day_is_replaced(self):
  from aidaily.publishing import daily
  from unittest.mock import patch
  import tempfile,json
  from pathlib import Path
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(daily.config,'DATA_ROOT',Path(tmp)),patch('aidaily.publishing.horizon_section.load_editions',return_value={'2026-11-03':{'items':[{'id':'x','title':'원문 기사','url':'https://example.com/a'}]}}):
    daily.record_horizon_publication('2026-11-03',{'status':'verification_failed'})
    path=Path(tmp)/'ai_news/horizon/published-history.json';self.assertFalse(path.exists())
    daily.record_horizon_publication('2026-11-03',{'status':'complete','exact_edition':True,'edition_sha256':__import__('hashlib').sha256(json.dumps({'items':[{'id':'x','title':'원문 기사','url':'https://example.com/a'}]},sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    daily.record_horizon_publication('2026-11-03',{'status':'complete','exact_edition':True,'edition_sha256':__import__('hashlib').sha256(json.dumps({'items':[{'id':'x','title':'원문 기사','url':'https://example.com/a'}]},sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    with self.assertRaisesRegex(RuntimeError,'changed'):
     daily.record_horizon_publication('2026-11-03',{'status':'complete','exact_edition':True,'edition_sha256':'different'})
    rows=json.loads(path.read_text());self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'published');self.assertEqual(rows[0]['items'][0]['url'],'https://example.com/a')
