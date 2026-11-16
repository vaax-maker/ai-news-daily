"""Reader-visible source attribution, state isolation and safe Horizon rendering."""
import copy,json,tempfile,unittest
from pathlib import Path
from aidaily.publishing import horizon_section as h
T={'color':{'accent':{'tech':'#264d44'},'text':{'tech.ink':'#111','tech.dim':'#555','tech.muted':'#777'},'line':{'tech':'#ddd'}}}
class HorizonSectionTests(unittest.TestCase):
 def edition(self):
  return {'date':'2026-11-03','status':'complete','pilot':{'start':'2026-11-03','end':'2026-11-09'},'items':[{'id':'hn:1','title':'실제 기사','url':'https://example.com/article/20001625','source_name':'Hacker News AI','source_type':'hackernews','published_at':'2026-11-02T15:00:00+00:00','published_at_note':'Hacker News 게시 시각','reason':'서빙 환경을 운영할 때 확인할 변경이다.','bullets':['실제 원문에 있는 변경 내용이다.','관련 조건도 함께 확인해야 한다.']}], 'sources':[{'name':'Hacker News AI','url':'https://news.ycombinator.com/','type':'hackernews','status':'ok','candidate_count':1}], 'metrics':{'candidate_count':1,'selected_count':1,'lookback_hours':72},'api_key':'NEVER_PUBLIC','raw_source':'NEVER_PUBLIC'}
 def test_sources_original_links_and_hn_timestamp_are_distinct(self):
  data=h.normalize_edition(self.edition(),'2026-11-03');page=h.render_section(data,'2026-11-03',T)
  self.assertIn('article/20001625',page);self.assertIn('원문 · example.com',page);self.assertIn('수집 · Hacker News AI',page);self.assertIn('Hacker News 게시 시각 11.03 00:00 KST',page);self.assertNotIn('발행 11.03',page);self.assertIn('최근 72시간',page);self.assertNotIn('NEVER_PUBLIC',page)
 def test_other_date_never_falls_back_to_todays_articles(self):
  page=h.render_section(h.normalize_edition(self.edition(),'2026-11-03'),'2026-11-02',T)
  self.assertNotIn('실제 기사',page);self.assertIn('이 날짜의 Horizon 브리핑이 없습니다',page);self.assertIn('data-horizon-date="2026-11-02"',page)
 def test_pending_is_not_empty_success_or_interim_article(self):
  data=self.edition();data['status']='pending';page=h.render_section(h.normalize_edition(data,data['date']),data['date'],T)
  self.assertIn('자료 선별을 진행',page);self.assertNotIn('실제 기사',page);self.assertNotIn('기준을 통과한 자료가 없습니다',page)
 def test_source_failure_and_zero_fresh_items_have_different_meaning(self):
  data=self.edition();data['sources'].append({'name':'문제 출처','url':'https://example.net/rss','type':'rss','status':'unavailable','candidate_count':0})
  normalized=h.normalize_edition(data,data['date']);self.assertEqual(normalized['status'],'partial');page=h.render_section(normalized,data['date'],T);self.assertIn('수집 확인 안 됨',page)
  data['sources'][-1]['status']='ok';normalized=h.normalize_edition(data,data['date']);self.assertEqual(normalized['status'],'complete');self.assertNotIn('수집 확인 안 됨',h.render_section(normalized,data['date'],T))
 def test_untrusted_content_and_unsafe_urls_do_not_execute(self):
  data=self.edition();data['items'][0]['title']='</script><script>alert(1)</script>'
  page=h.render_section(h.normalize_edition(data,data['date']),data['date'],T);self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
  for url in ['javascript:alert(1)','https://user:secret@example.com/','https://example.com/\nsecret']:
   with self.subTest(url=url):
    data=self.edition();data['items'][0]['url']=url
    with self.assertRaises(ValueError):h.normalize_edition(data,data['date'])
 def test_loader_keeps_corrupt_edition_failure_and_running_state_separate(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'editions').mkdir();(root/'runs').mkdir();(root/'editions/2026-11-03.json').write_text('{bad');(root/'editions/2026-99-99.json').write_text('{}');(root/'runs/2026-11-04.json').write_text(json.dumps({'status':'enriching','secret':'NEVER_PUBLIC'}));data=h.load_editions(root)
   self.assertEqual(data['2026-11-03']['status'],'invalid');self.assertEqual(data['2026-11-04']['status'],'running');self.assertNotIn('2026-99-99',data);self.assertNotIn('NEVER_PUBLIC',json.dumps(data))
 def test_completed_empty_and_trial_end_are_explicit(self):
  data=self.edition();data['items']=[];page=h.render_section(h.normalize_edition(data,data['date']),data['date'],T);self.assertIn('이번 기준을 통과한 자료가 없습니다',page)
  page=h.render_section(None,'2026-11-10',T,pilot=data['pilot']);self.assertIn('시범 운영 종료',page)
  page=h.render_section(None,'2026-11-02',T,pilot=data['pilot']);self.assertIn('시범 시작 전',page);self.assertNotIn('시범 운영 종료',page)
