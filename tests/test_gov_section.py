import copy,unittest
from unittest.mock import patch
from io import BytesIO
from aidaily.publishing import gov_section as g,gov_verification as v
T={'color':{'accent':{'tech':'#264d44'},'text':{'tech.ink':'#111','tech.dim':'#555'},'line':{'tech':'#ddd'}}}
class GovSectionTests(unittest.TestCase):
 def data(self):return {'date':'2026-11-04','status':'partial','baseline':True,'items':[{'id':'PBLN_12345','title':'AI 기술 지원','url':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_12345','source_name':'기업마당','agency':'중기부','published_date':'2026-11-03','application_period':'2026-11-03~2026-11-10','summary':'개발기업 대상 지원사업이다.','labels':['기준판'],'change_note':''}],'sources':[{'id':'bizinfo','name':'기업마당','url':'https://www.bizinfo.go.kr/','status':'ok','count':200},{'id':'msit','name':'과기정통부','url':'https://www.msit.go.kr/','status':'auth_required'}],'raw_key':'SECRET'}
 def test_baseline_does_not_claim_today_new_and_sources_have_different_status(self):
  d=g.normalize_edition(self.data(),'2026-11-04');page=g.render_section(d,d['date'],T)
  self.assertIn('오늘 새로 나온 공고라는 뜻은 아닙니다',page);self.assertIn('확인 준비 중',page);self.assertIn('12345',page);self.assertNotIn('SECRET',page)
 def test_date_change_has_no_current_notices(self):
  page=g.render_section(self.data(),'2026-11-03',T);self.assertNotIn('AI 기술 지원',page);self.assertIn('기록이 없습니다',page)
 def test_failure_is_not_empty_success_and_escapes_prose(self):
  d=self.data();d['status']='failed';page=g.render_section(d,d['date'],T);self.assertNotIn('표시할 대상 공고가 없습니다',page);self.assertIn('확인하지 못했습니다',page)
  d=self.data();d['items'][0]['title']='<script>alert(1)</script>';page=g.render_section(g.normalize_edition(d,d['date']),d['date'],T);self.assertNotIn('<script>',page)
 def test_invalid_urls_and_duplicate_ids_rejected(self):
  for url in ['javascript:alert(1)','https://u:p@example.org/','https://example.com/notice','https://www.bizinfo.go.kr/api?crtfcKey=TEST_ONLY_KEY','https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_12345&serviceKey=TEST_ONLY_KEY']:
   d=self.data();d['items'][0]['url']=url
   with self.assertRaises(ValueError):g.normalize_edition(d,d['date'])
  d=self.data();d['sources'][0]['url']='https://www.bizinfo.go.kr/api?crtfcKey=TEST_ONLY_KEY'
  self.assertNotIn('TEST_ONLY_KEY',g.render_section(g.normalize_edition(d,d['date']),d['date'],T))
  d=self.data();d['items'][0]['id']='PBLN_OTHER'
  with self.assertRaises(ValueError):g.normalize_edition(d,d['date'])
  d=self.data();d['items']*=2
  with self.assertRaises(ValueError):g.normalize_edition(d,d['date'])
 def verify(self,data,page):
  response=BytesIO(page.encode());response.status=200
  with patch.object(v,'load_editions',return_value={data['date']:data}):return v.verify_gov_publication(data['date'],opener=lambda *a,**k:response)
 def test_verifier_checks_matching_notice_and_exact_date(self):
  d=g.normalize_edition(self.data(),'2026-11-04');page=g.render_section(d,d['date'],T);self.assertTrue(self.verify(d,page)['exact_edition'])
  for bad in [page.replace('data-gov-date="2026-11-04"','data-gov-date="2026-11-03"'),page.replace('PBLN_12345','PBLN_99999'),page.replace('중기부','다른 기관')]:
   with self.assertRaises(RuntimeError):self.verify(d,bad)

 def test_matching_notice_outside_government_section_cannot_pass(self):
  import re
  d=g.normalize_edition(self.data(),'2026-11-04');page=g.render_section(d,d['date'],T)
  article=re.search(r'<tr data-gov-item=.*?</tr>',page,re.S).group(0)
  altered=page.replace(article,'')+article
  with self.assertRaises(RuntimeError):self.verify(d,altered)

 def test_confirmation_time_is_korean_local_and_not_original_publication(self):
  d=self.data();d['checked_at']='2026-11-03T23:50:34+00:00'
  page=g.render_section(g.normalize_edition(d,d['date']),d['date'],T)
  self.assertIn('최종 확인 2026.11.04 08:50 KST',page);self.assertIn('2026.11.03',page)
  self.assertNotIn('23:50:34+00:00',page)

 def test_three_official_sources_and_each_identity_date_meaning(self):
  cases=[('msit:100:123','https://www.msit.go.kr/bbs/view.do?sCode=user&mId=311&mPid=121&bbsSeqNo=100&nttSeqNo=123','과학기술정보통신부','게시일'),('koneps:R26BK123:000','https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK123&bidPbancOrd=000','나라장터','공고일')]
  for identity,url,source,label in cases:
   d=self.data();d['items'][0].update(id=identity,url=url,source_name='잘못된 출처')
   data=g.normalize_edition(d,d['date']);page=g.render_section(data,d['date'],T)
   self.assertEqual(data['items'][0]['source_name'],source);self.assertIn(g.source_display(data['items'][0]),page);self.assertIn('2026.11.03',page);self.assertTrue(self.verify(data,page)['exact_edition'])
   d['items'][0]['id']='mismatched'
   with self.assertRaises(ValueError):g.normalize_edition(d,d['date'])
   d['items'][0]['id']=identity;d['items'][0]['url']=url+'&serviceKey=TEST_ONLY_KEY'
   with self.assertRaises(ValueError):g.normalize_edition(d,d['date'])

 def test_result_notices_and_tenders_are_distinguished_from_grants(self):
  d=self.data();d['items'][0]['title']='기술개발사업 신규과제 선정결과 공고'
  n=g.normalize_edition(d,d['date']);self.assertEqual(n['items'][0]['notice_kind'],'선정결과')
  self.assertIn('선정결과',g.render_section(n,d['date'],T))

 def test_table_has_exact_four_fields_and_title_link_only(self):
  d=self.data();d['items'][0]['published_at']='2026-11-03 13:51:34'
  d=g.normalize_edition(d,d['date']);page=g.render_section(d,d['date'],T)
  p=v._Notices();p.feed(page)
  self.assertEqual([''.join(x)for x in p.headers],['일시','출처','기관명','제목'])
  self.assertEqual(len(p.items['PBLN_12345'][0]['cells']),4)
  self.assertIn('13:51:34',page);self.assertNotIn('개발기업 대상 지원사업이다.',page)
  self.assertTrue(self.verify(d,page)['four_column_table'])
  with self.assertRaises(RuntimeError):self.verify(d,page.replace('>기관명</th>','>담당기관</th>'))
 def test_date_only_does_not_invent_midnight_and_missing_agency_is_explicit(self):
  d=self.data();d['items'][0]['agency']='';d=g.normalize_edition(d,d['date'])
  self.assertEqual(g.notice_time(d['items'][0]),'2026.11.03')
  page=g.render_section(d,d['date'],T);self.assertNotIn('00:00',page);self.assertIn('기관 미확인',page);self.assertTrue(self.verify(d,page)['exact_edition'])
 def test_rows_outside_the_actual_table_do_not_satisfy_verification(self):
  import re
  d=g.normalize_edition(self.data(),'2026-11-04');page=g.render_section(d,d['date'],T)
  row=re.search(r'<tr data-gov-item=.*?</tr>',page,re.S).group(0)
  outside=page.replace(row,'').replace('</table>','</table>'+row)
  with self.assertRaises(RuntimeError):self.verify(d,outside)
