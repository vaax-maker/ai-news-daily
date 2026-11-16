import argparse,tempfile,unittest,json
from pathlib import Path
from unittest import mock
from aidaily.customer_stories import pipeline as p,checkpoint
from aidaily.integrations import openrouter

class ResumeTests(unittest.TestCase):
 def test_pending_freezes_collection_and_candidate_and_blocks_outputs(self):
  with tempfile.TemporaryDirectory() as folder:
   args=argparse.Namespace(dump_dir='fixture',since='1d',date='2026-10-02',docs_root=folder+'/docs')
   gen={'title':'fixture','items':[{'issue':'로컬 전사 설정','content':'설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.','sources':['source'],'refs':['R1']}],'overview':'fixture'};calls=[]
   def evaluator(g,c):
    calls.append((json.dumps(g,sort_keys=True),c))
    if len(calls)==1:raise openrouter.CompletionPending('same-job')
    return {'passed':True,'evidence_issues':[],'judge':{'ok':True,'fabrication':False,'pii':False}}
   with mock.patch.object(p,'load_corpus',return_value='original'),mock.patch.object(p,'load_seen',return_value={}),mock.patch.object(p,'load_jsonl_rooms',return_value=([],['frozen-hash'])),mock.patch.object(p,'build_multi_corpus',return_value=('[R1] 설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.\n'+'original'*150,['source'],['original-url'],{})) as collect,mock.patch.object(p,'generate',return_value=gen) as generate,mock.patch.object(p,'evaluate',side_effect=evaluator),mock.patch.object(p,'render_customer_stories',return_value='fixture html'),mock.patch.object(p,'load_manifest',return_value=[]),mock.patch.object(p,'upsert_manifest',return_value=[]),mock.patch.object(p,'render_archive_index',return_value='fixture archive'),mock.patch.object(p,'write_open_chat_community_page',return_value=('fixture',0)),mock.patch.object(p,'save_seen') as save_seen,mock.patch.object(p,'trim_jsonl'):
    with checkpoint.locked(folder,args.date) as saved:
     with self.assertRaises(openrouter.CompletionPending):p._run(args,folder,saved)
    self.assertFalse(Path(args.docs_root).exists());save_seen.assert_not_called()
    collect.return_value=('changed'*150,['new'],['new-url'],{})
    with checkpoint.locked(folder,args.date) as saved:p._run(args,folder,saved)
    self.assertEqual(calls[0],calls[1]);self.assertEqual(generate.call_count,1);self.assertEqual(collect.call_count,1)
    self.assertTrue((Path(folder)/'latest.json').exists());self.assertEqual(json.loads((Path(folder)/'checkpoints'/f'{args.date}.json').read_text())['stage'],'complete')
    with checkpoint.locked(folder,args.date) as saved:p._run(args,folder,saved)
    self.assertEqual(generate.call_count,1);self.assertEqual(collect.call_count,1)
 def test_next_day_main_resumes_original_business_date(self):
  with tempfile.TemporaryDirectory() as folder:
   data=Path(folder)/'customer_stories'
   with checkpoint.locked(data,'2026-10-02') as saved:saved.save(stage='evaluating',gen={'title':'original'},inputs={'corpus':'original'})
   with mock.patch.object(p.config,'DATA_ROOT',Path(folder)),mock.patch('sys.argv',['pipeline','--date','2026-10-03']),mock.patch.object(p,'_run') as run:
    p.main()
    args,root,saved=run.call_args.args
    self.assertEqual(args.date,'2026-10-02');self.assertEqual(saved.state['gen']['title'],'original')
 def test_unknown_judgment_cannot_pass(self):
  for judgment in [{'ok':None},{'ok':True},{'ok':'true','fabrication':False,'pii':False}]:
   with mock.patch.object(p,'judge',return_value=judgment):
    with self.assertRaises(openrouter.RoutingBlocked):p.evaluate({},'fixture')
 def test_new_run_does_not_discard_active_work(self):
  with tempfile.TemporaryDirectory() as folder:
   with checkpoint.locked(folder,'2026-10-02') as saved:
    saved.save(stage='evaluating',gen={'title':'fixture'})
    with self.assertRaises(openrouter.RoutingBlocked):saved.restart()
    self.assertEqual(saved.state['stage'],'evaluating')
    self.assertEqual(saved.path.stat().st_mode&0o777,0o600)
if __name__=='__main__':unittest.main()

class TerminalDailyDecisionTests(unittest.TestCase):
 def test_review_and_empty_content_do_not_block_next_days_collection(self):
  with tempfile.TemporaryDirectory() as folder:
   with checkpoint.locked(folder,'2026-10-10') as saved:saved.save(stage='review',gen={'title':'needs review'},inputs={'corpus':'frozen'})
   with checkpoint.locked(folder,'2026-10-11') as saved:saved.save(stage='complete',status='no_information',gen={'items':[]},inputs={'corpus':'frozen empty information'})
   self.assertEqual(checkpoint.unfinished_date(folder,'2026-10-13'),'2026-10-13')
   self.assertEqual(json.loads((Path(folder)/'checkpoints/2026-10-10.json').read_text())['gen']['title'],'needs review')
 def test_pending_work_still_resumes_oldest_day(self):
  with tempfile.TemporaryDirectory() as folder:
   with checkpoint.locked(folder,'2026-10-10') as saved:saved.save(stage='review',gen={'title':'review'})
   with checkpoint.locked(folder,'2026-10-11') as saved:saved.save(stage='evaluating',gen={'title':'accepted work'})
   with checkpoint.locked(folder,'2026-10-12') as saved:saved.save(stage='collected',inputs={'corpus':'not generated yet'})
   self.assertEqual(checkpoint.unfinished_date(folder,'2026-10-13'),'2026-10-11')
