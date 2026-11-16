import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aidaily import config
from aidaily.publishing import daily
class GovDailyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.date='2026-11-04';self.calls=[]
  p=self.root/'data/ai_news/gov/settings.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'enabled':True,'start':self.date}))
  self.patch=patch.multiple(config,PROJECT_ROOT=self.root,DATA_ROOT=self.root/'data',DOCS_ROOT=self.root/'docs',PUBLISHING_REPOSITORY=self.root/'site');self.patch.start();self.addCleanup(self.patch.stop)
 def run_day(self,command):
  with patch.object(daily,'customer_generated',return_value=True),patch.object(daily,'today_generated',return_value=True),patch.object(daily,'verify_publication',return_value={'http_status':200}),patch.object(daily.subprocess,'run',side_effect=command):daily.run_day(self.date,adopt_generated=True,no_notify=True)
  return json.loads((self.root/'data/publishing/daily_runs'/f'{self.date}.json').read_text())
 def test_optional_timeout_does_not_suppress_news_publication(self):
  def command(args,**kw):
   self.calls.append(args[2])
   if args[2]=='aidaily.ai_news.gov':
    p=self.root/'data/ai_news/gov/runs'/f'{self.date}.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'status':'submission_unknown','request_id':'same-run'}));raise subprocess.TimeoutExpired(args,180)
   return SimpleNamespace(returncode=0)
  state=self.run_day(command);self.assertEqual(state['status'],'published_unnotified');self.assertEqual(state['stages']['gov']['status'],'pending');self.assertIn('aidaily.publishing.pipeline',self.calls)
 def test_exit_zero_without_a_valid_edition_is_not_empty_success(self):
  state=self.run_day(lambda *a,**k:SimpleNamespace(returncode=0));self.assertEqual(state['stages']['gov']['status'],'failed');self.assertEqual(state['stages']['publish']['status'],'complete')
 def test_late_edition_changes_publication_input_fingerprint(self):
  old=daily.fingerprint(daily.publication_inputs(self.date));p=daily.generation_outputs('gov',self.date)[0];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{"date":"2026-11-04","status":"partial"}');self.assertNotEqual(old,daily.fingerprint(daily.publication_inputs(self.date)))
