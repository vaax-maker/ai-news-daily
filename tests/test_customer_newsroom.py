import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from aidaily.customer_stories import newsroom,newsroom_topics
from aidaily.integrations import openrouter,public_research

class NewsroomTests(unittest.TestCase):
 def test_public_official_numeric_url_survives_prose_redaction_and_index(self):
  from aidaily.publishing.search_index import _customer_story_v2_rows
  from aidaily.customer_stories.story_render import render_story_report
  url='https://help.openai.com/en/articles/20001625-understanding-chatgpt-and-codex-usage-limits'
  report=self.report();item=report['items'][0]
  item['background'][0].update(url=url,text='공식 안내에 사용 한도가 설명되어 있다.')
  item['related_links']=[{'url':url,'label':'공식 안내'}]
  item['voices'][0]['url']='https://private.invalid/room/18472466542857243'
  item['commentary']='내부 식별자 18472466542857243는 공개하지 않는다.'
  public=newsroom.public_copy(report);story=public['items'][0]
  self.assertEqual(story['background'][0]['url'],url)
  self.assertEqual(story['related_links'][0]['url'],url)
  self.assertNotIn('url',story['voices'][0])
  self.assertNotIn('18472466542857243',story['commentary'])
  row=_customer_story_v2_rows(public,'2026-11-03','https://example.org/')[0]
  self.assertEqual(row['story_content']['background'][0]['url'],url)
  rendered=render_story_report(public,'2026-11-03')
  self.assertIn('공식 안내에 사용 한도가 설명되어 있다.',rendered)
  self.assertIn(url,rendered)

 def test_public_copy_omits_unsafe_urls(self):
  report=self.report();report['items'][0]['related_links']=[{'url':'javascript:alert(1)','label':'위험'}, {'url':'https://user:pass@example.com/','label':'위험'}]
  rows=newsroom.public_copy(report)['items'][0]['related_links']
  self.assertTrue(all('url' not in row for row in rows))

 def test_review_packet_deduplicates_sources_and_preserves_input(self):
  report=self.report()
  prompt={'evidence':[{'evidence_id':'e1','text':'one'},{'evidence_id':'e2','text':'two'},{'evidence_id':'unused','text':'other'}],
          'research':[{'url':'https://docs.x.ai/grok-bot/overview','text':'Bots use a cloud computer.'},
                      {'url':'https://docs.x.ai/grok-bot/overview','text':'Bots use a cloud computer.'},
                      {'url':'https://example.com/unused','text':'not referenced'}],
          'previous_publications':['older']}
  before_report=copy.deepcopy(report);before_prompt=copy.deepcopy(prompt)
  packet=newsroom.review_packet(report,prompt)
  self.assertEqual(report,before_report);self.assertEqual(prompt,before_prompt)
  self.assertNotIn('source_excerpt',packet['report']['items'][0]['background'][0])
  self.assertEqual([e['evidence_id'] for e in packet['evidence']],['e1','e2'])
  self.assertEqual([r['url'] for r in packet['research']],['https://docs.x.ai/grok-bot/overview'])

 def test_limits_event_requires_both_products_and_groups_once(self):
  texts=['ChatGPT와 Codex의 사용량 한도가 공유되나요?',
         'Codex와 챗GPT 한도 통합이 궁금해요.',
         'Codex에서 GPT-5 모델의 한도는 얼마인가요?',
         'Codex 사용량 한도가 궁금합니다.',
         'ChatGPT 사용량 한도가 궁금합니다.']
  rows=[{'evidence_id':f'e{i}','source_id':f's{i%2}','date':'2026-11-03',
         'text':v,'already_published':False} for i,v in enumerate(texts)]
  research={'chatgpt-codex-limits':{'sources':[{'url':'https://help.openai.com/en/articles/20001625','verified':True,'primary':True}]}}
  topics,selection=newsroom_topics.discovery({'evidence':rows},research,{'selection':{'minimum_observations':2,'minimum_days':2,'minimum_sources':2,'maximum_topics':2}})
  buckets={t['topic_id']:[x['evidence_id'] for x in t['observations']] for t in topics}
  self.assertEqual(buckets['chatgpt-codex-limits'],['e0','e1'])
  self.assertEqual(len([eid for group in buckets.values() for eid in group]),len(set(eid for group in buckets.values() for eid in group)))
  event=next(x for x in selection['candidates'] if x['topic_id']=='chatgpt-codex-limits')
  self.assertTrue(event['eligible']);self.assertEqual(event['distinct_sources'],2)

 def test_candidate_sample_prefers_new_recent_and_varied_sources(self):
  def observation(eid,source,date,published=False):
   return dict(evidence_id=eid,source_id=source,date=date,already_published=published,kind='experience')
  rows=[observation('old','s1','2026-10-21'),observation('new','s1','2026-11-03'),
        observation('other','s2','2026-11-02'),observation('published','s3','2026-11-03',True)]
  pool={r['evidence_id']:{'private':True} for r in rows}
  self.assertEqual([r['evidence_id'] for r in newsroom.candidate_sample({'observations':rows},pool,2)],['new','other'])
  self.assertEqual(newsroom.candidate_sample({'observations':rows},pool,4)[-1]['evidence_id'],'published')

 def test_empty_initial_draft_stops_before_audit(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot']}),json.dumps({'title':'','overview':'','items':[]})])
   self.assertEqual(self.execute(root,model),2)
   self.assertEqual(model.call_count,2)
   saved=json.loads((root/'data/customer_stories/newsroom/2026-11-02.json').read_text())
   self.assertEqual(saved['stage'],'no_candidates');self.assertFalse((root/'docs').exists())

 def test_empty_repaired_draft_stops_before_audit(self):
  with tempfile.TemporaryDirectory() as d:
   invalid=self.report();invalid['items'][0]['evidence_ids']=['missing']
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot']}),json.dumps(invalid),json.dumps({'title':'','overview':'','items':[]})])
   self.assertEqual(self.execute(root,model),2)
   self.assertEqual(model.call_count,3)
   saved=json.loads((root/'data/customer_stories/newsroom/2026-11-02.json').read_text())
   self.assertEqual(saved['stage'],'no_candidates');self.assertFalse((root/'docs').exists())

 def test_resumed_empty_rejection_does_not_call_model(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder=root/'data/customer_stories/newsroom';folder.mkdir(parents=True)
   (folder/'2026-11-02.json').write_text(json.dumps({'stage':'support_review_required','report':{'items':[]}}))
   model=mock.Mock(side_effect=AssertionError('unexpected model call'))
   self.assertEqual(self.execute(root,model),2);self.assertEqual(model.call_count,0)
   self.assertEqual(json.loads((folder/'2026-11-02.json').read_text())['stage'],'no_candidates')

 def test_repair_receives_research_aliases_and_resolves_them(self):
  with tempfile.TemporaryDirectory() as d:
   initial=self.report();initial['items'][0]['evidence_ids']=['missing']
   fixed=self.report();item=fixed['items'][0]
   item['evidence_ids']=['E1','E2'];item['voices'][0]['evidence_ids']=['E1','E2']
   item['background'][0]={'research_id':'F1','text':'공식 문서는 클라우드 환경 작업을 설명한다.','label':'공식 문서'}
   model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot']}),json.dumps(initial),json.dumps(fixed),json.dumps(dict(ok=True,supported=True,privacy=True,not_duplicate=True,issues=[]))])
   root=Path(d);self.assertEqual(self.execute(root,model),0)
   repair=json.loads(model.call_args_list[2].args[1])
   self.assertIn('F1',[r.get('research_id') for r in repair['official_sources']])
   self.assertEqual({r['evidence_id'] for r in repair['evidence']},{'E1','E2'})
   saved=json.loads((root/'data/customer_stories/newsroom/2026-11-02.json').read_text())
   self.assertEqual(saved['report']['items'][0]['background'][0]['url'],'https://docs.x.ai/grok-bot/overview')
   self.assertEqual(set(saved['report']['items'][0]['evidence_ids']),{'e1','e2'})

 def test_short_model_references_resolve_to_frozen_ids_and_urls_only(self):
  report=self.report();item=report['items'][0];item['evidence_ids']=['E1'];item['voices'][0]['evidence_ids']=['E1']
  item['background'][0].update(research_id='F1',url='https://invented.example/')
  restored=newsroom.restore_refs(report,{'E1':'e1'},{'F1':{'url':'https://docs.x.ai/grok-bot/overview','text':'Bots use a cloud computer.'}})
  self.assertEqual(restored['items'][0]['evidence_ids'],['e1'])
  self.assertEqual(restored['items'][0]['background'][0]['url'],'https://docs.x.ai/grok-bot/overview')
  item['evidence_ids']=['E999']
  self.assertEqual(newsroom.restore_refs(report,{'E1':'e1'},{} )['items'][0]['evidence_ids'],['E999'])
 def test_duplicate_review_is_mandatory_even_when_general_judge_is_advisory(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot']}),json.dumps(self.report()),json.dumps(dict(ok=False,supported=True,privacy=True,not_duplicate=False,issues=['same event']))])
   with self.assertRaises(ValueError):self.execute(root,model)
   self.assertFalse((root/'docs').exists())
   with self.assertRaises(ValueError):self.execute(root,model)
   self.assertEqual(model.call_count,3)
 def test_machine_story_identity_is_not_redacted_as_a_private_number(self):
  report=self.report();report['items'][0]['story_id']='bot-purpose-20261102'
  self.assertEqual(newsroom.public_copy(report)['items'][0]['story_id'],'bot-purpose-20261102')
 def dossier(self):
  return dict(evidence=[dict(evidence_id='e1',text='그록봇은 어떤 작업에 쓰나요?',source_id='s1',sources=['오픈채팅 · 모임 1'],source='오픈채팅 · 모임 1',observed_dates=['2026-11-01'],date='2026-11-01',url='',private=True,already_published=False),dict(evidence_id='e2',text='Grok Bot 활용 사례가 궁금합니다.',source_id='s2',sources=['오픈채팅 · 모임 2'],source='오픈채팅 · 모임 2',observed_dates=['2026-11-02'],date='2026-11-02',url='',private=True,already_published=False)],coverage={'complete':False},history=[])
 def report(self):
  return dict(title='개인비서 선택',overview='무슨 일을 맡길 수 있을까.',items=[dict(story_id='bot-purpose',issue='봇에 맡길 일을 정하는 법',dek='반복된 활용 질문을 공식 문서와 대조했다.',article_kind='explainer',evidence_ids=['e1','e2'],background=[dict(text='공식 문서는 클라우드 환경 작업을 설명한다.',url='https://docs.x.ai/grok-bot/overview',label='공식 문서',source_excerpt='Bots use a cloud computer.')],voices=[dict(text='활용할 작업과 사례를 묻는 질문이 나왔다.',source='오픈채팅 · 모임 1',date='',evidence_ids=['e1','e2'])],timeline=[],commentary='완료 기준을 정해야 한다.',related_links=[])])
 def execute(self,root,model,blocking=False):
  args=SimpleNamespace(date='2026-11-02',docs_root=str(root/'docs'))
  research={'sources':[dict(url='https://docs.x.ai/grok-bot/overview',text='Bots use a cloud computer.',primary=True,verified=True)]}
  with mock.patch('aidaily.customer_stories.pipeline._ai_judge_enabled',return_value=blocking),mock.patch.object(newsroom.config,'DATA_ROOT',root/'data'),mock.patch('aidaily.customer_stories.sources.fetch_all',return_value={}),mock.patch('aidaily.customer_stories.pipeline.load_jsonl_rooms',return_value=({},[])),mock.patch.object(newsroom.rolling_inputs,'gather',return_value=self.dossier()),mock.patch.object(newsroom.public_research,'research',return_value=research),mock.patch.object(newsroom.openrouter,'complete',model):
   return newsroom.run_until_settled(args)
 def test_full_run_freezes_input_resumes_and_hides_private_verification(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot'],'reason':'repeated question'}),json.dumps(self.report()),json.dumps(dict(ok=True,supported=True,privacy=True,not_duplicate=True,issues=[]))])
   self.assertEqual(self.execute(root,model),0);self.assertEqual(model.call_count,3)
   data=json.loads((root/'data/customer_stories/2026-11-02.json').read_text())
   self.assertEqual(data['gen']['schema_version'],2)
   self.assertNotIn('source_excerpt',json.dumps(data))
   self.assertNotIn('publication_index',data['gen']['items'][0])
   self.assertTrue((root/'docs/v2/uservoice/2026-11-02.html').exists())
   self.assertEqual(self.execute(root,model),0);self.assertEqual(model.call_count,3)
 def test_pending_preserves_same_input_without_public_files(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);model=mock.Mock(side_effect=openrouter.CompletionPending('same'))
   with self.assertRaises(openrouter.CompletionPending):self.execute(root,model)
   saved=json.loads((root/'data/customer_stories/newsroom/2026-11-02.json').read_text())
   self.assertEqual(saved['stage'],'researched');self.assertIn('dossier',saved)
   self.assertFalse((root/'docs').exists())
 def test_failed_review_preserves_candidate_no_retry_or_publication(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot'],'reason':'repeated question'}),json.dumps(self.report()),json.dumps(dict(ok=False,supported=False,privacy=True,not_duplicate=True,issues=['unsupported']))])
   with self.assertRaises(ValueError):self.execute(root,model,blocking=True)
   with self.assertRaises(ValueError):self.execute(root,model,blocking=True)
   self.assertEqual(model.call_count,3);self.assertFalse((root/'docs').exists())
 def test_invented_fact_excerpt_blocks_before_review(self):
  with tempfile.TemporaryDirectory()as d:
   report=self.report();report['items'][0]['background'][0]['source_excerpt']='fabricated source excerpt'
   root=Path(d);model=mock.Mock(side_effect=[json.dumps({'selected_topic_ids':['grok-bot'],'reason':'repeated question'}),json.dumps(report),json.dumps(report)])
   with self.assertRaises(ValueError):self.execute(root,model)
   self.assertEqual(model.call_count,3);self.assertFalse((root/'docs').exists())

class ResearchTests(unittest.TestCase):
 def test_private_text_never_becomes_a_query_and_unofficial_hits_rejected(self):
  search=mock.Mock(return_value=(b'<rss><channel><item><link>https://evil.example/a</link></item></channel></rss>',{}))
  fetch=mock.Mock(return_value='Official public product description. '*20)
  result=public_research.research('grok-bot',searcher=search,fetcher=fetch)
  self.assertEqual(len(result['sources']),2)
  self.assertIn('Grok+Bot+official+documentation',search.call_args.args[0])
  self.assertFalse(any('evil.example'in call.args[0]for call in fetch.call_args_list))
  self.assertEqual(public_research.research('personal room text',searcher=search,fetcher=fetch)['status'],'unconfigured')
 def test_search_failure_does_not_turn_snippet_into_fact(self):
  result=public_research.research('grok-bot',searcher=mock.Mock(side_effect=OSError),fetcher=mock.Mock(side_effect=OSError))
  self.assertEqual(result['status'],'unavailable');self.assertEqual(result['sources'],[])

if __name__=='__main__':unittest.main()
