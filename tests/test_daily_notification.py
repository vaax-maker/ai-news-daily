import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.notifications import daily_digest as d

class DailyNotificationTests(unittest.TestCase):
    def test_today_only_individual_reports_room_cap_and_override(self):
        rows=[{'id':'n','date':'2026-10-13','kind':'ai_news','title':'news'}]
        rows +=[{'id':str(i),'date':'2026-10-12','kind':'customer_story','channel':'room','title':'customer'}for i in range(6)]
        rows +=[{'id':'b','date':'2026-10-13','kind':'youtube_summary','pub':'브리프'},{'id':'y','date':'2026-10-13','kind':'youtube_summary','pub':'개별리포트','title':'video'}]
        override={'enabled':True,'display_date':'2026-10-13','source_date':'2026-10-12','source':'고객사용기'}
        self.assertEqual(len(d.published_articles(rows,'2026-10-13',override)),6)
        self.assertEqual(d.published_articles(rows,'2026-10-14',override),[])
        self.assertEqual(d.published_articles(rows[1:7],'2026-10-13',override),[])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'s').write_text(json.dumps(rows));(p/'o').write_text(json.dumps(override))
            caption=d.build_caption({'date':'2026-10-13'},p/'s',p/'o',p/'missing')
            self.assertIn('고객 사용기 4건 (10/12 발행 자료 포함)',caption)
            self.assertLess(caption.index('AI뉴스'),caption.index('YouTube 요약'))
    def test_keyword_quotes_require_same_day_and_literal_published_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'s').write_text(json.dumps([{'id':'n','date':'2026-10-13','kind':'ai_news','title':'news','summary_bullets':['literal fact']}]))
            (p/'k').write_text(json.dumps({'date':'2026-10-13','items':[{'id':'n','keyword':'모델','quote':'literal fact'},{'id':'n','keyword':'fake','quote':'invented'}]}))
            caption=d.build_caption({'date':'2026-10-13'},p/'s',p/'none',p/'k')
            self.assertIn('모델: “literal fact”',caption);self.assertNotIn('invented',caption)
            self.assertEqual(d.build_caption({'date':'2026-10-14'},p/'s',p/'none',p/'k'),'')
    def test_sent_receipt_prevents_duplicate_and_never_sends_image(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(d.telegram,'send_photo',return_value={'result':{'message_id':1}}) as send:
            self.assertEqual(d.send_once('2026-10-13','text','token','chat',tmp)['status'],'sent')
            self.assertEqual(d.send_once('2026-10-13','text','token','chat',tmp)['status'],'skipped_existing_receipt')
            send.assert_called_once_with('','text','token','chat')
    def test_uncertain_or_sending_receipt_never_resubmits(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(d.telegram,'send_photo',side_effect=TimeoutError) as send:
            with self.assertRaises(TimeoutError):d.send_once('2026-10-13','text','token','chat',tmp)
            self.assertEqual(json.loads((Path(tmp)/'2026-10-13.json').read_text())['status'],'uncertain')
            d.send_once('2026-10-13','text','token','chat',tmp);self.assertEqual(send.call_count,1)
            (Path(tmp)/'2026-10-14.json').write_text('{"status":"sending"}')
            d.send_once('2026-10-14','text','token','chat',tmp);self.assertEqual(send.call_count,1)
    def test_dry_run_never_reads_credentials_or_sends_or_writes_receipt(self):
        with patch('sys.argv',['daily_digest','--dry-run']),patch.object(d,'build_caption',return_value='preview'),patch.object(d,'verified_government_count',return_value=None),patch.object(d,'load_credentials') as creds,patch.object(d,'send_once') as send,patch('builtins.print'):
            d.main();creds.assert_not_called();send.assert_not_called()

    def test_caption_uses_exact_renderer_visible_counts(self):
        rows=[]
        for kind,source,count in [('ai_news','AI뉴스',11),('youtube_summary','오늘 유튜브',9),('customer_story','고객사용기',13)]:
            for i in range(count):
                rows.append({'id':kind+str(i),'date':'2026-10-13','kind':kind,'source':source,'cat':'tech','pub':'개별리포트','channel':('room'+str(min(i//4,2))) if kind=='customer_story' else source,'title':'기사'})
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'store').write_text(json.dumps(rows))
            caption=d.build_caption({'date':'2026-10-13'},p/'store',p/'customer-date-override.json',p/'keywords')
        self.assertIn('AI뉴스 11건',caption)
        self.assertIn('YouTube 요약 9건',caption)
        self.assertIn('고객 사용기 12건',caption)


class GovernmentCountNotificationTests(unittest.TestCase):
    def caption(self, root, date='2026-11-04'):
        (root/'store').write_text(json.dumps([{'id':'n','date':date,'kind':'ai_news','title':'기존 기사'}]))
        return d.build_caption({'date':date},root/'store',root/'none',root/'none',gov_root=root/'gov')

    def edition(self, root, status='complete', items=2, date='2026-11-04'):
        p=root/'gov/editions';p.mkdir(parents=True,exist_ok=True)
        notices=[{'id':f'PBLN_00000000000000{i:02d}','title':f'정부과제 개별제목 {i}',
                  'url':f'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_00000000000000{i:02d}'} for i in range(items)]
        (p/(date+'.json')).write_text(json.dumps({'date':date,'status':status,'items':notices,'sources':[],
            'metrics':{'fetched_count':200,'relevant_count':58,'shown_count':99}}))

    def test_only_displayed_notice_count_no_titles_or_collection_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.edition(root);caption=self.caption(root)
        self.assertIn('정부과제 2건',caption)
        self.assertNotIn('정부과제 개별제목',caption)
        self.assertNotIn('200',caption);self.assertNotIn('58건',caption);self.assertNotIn('99건',caption)
        self.assertEqual([x for x in caption.splitlines() if '정부과제' in x],['정부과제 2건'])

    def test_partial_zero_and_absent_or_failed_have_distinct_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.assertNotIn('정부과제',self.caption(root))
            self.edition(root,'partial',1);self.assertIn('정부과제 1건',self.caption(root))
            self.edition(root,'complete',0);self.assertIn('정부과제 0건',self.caption(root))
            self.edition(root,'failed',1);self.assertNotIn('정부과제',self.caption(root))
            self.edition(root,'complete',1,date='2026-11-03')
            self.assertNotIn('정부과제',self.caption(root,date='2026-11-05'))

    def test_actual_sender_omits_unverified_government_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.edition(root)
            (root/'store').write_text(json.dumps([{'id':'n','date':'2026-11-04','kind':'ai_news','title':'기존 기사'}]))
            caption=d.build_caption({'date':'2026-11-04'},root/'store',root/'none',root/'none',gov_root=root/'gov',gov_count=None)
        self.assertNotIn('정부과제',caption);self.assertIn('기존 기사',caption)
        from aidaily.publishing import gov_verification
        with patch.object(gov_verification,'verify_gov_publication',return_value={'date':'2026-11-04','status':'complete','items':10,'exact_edition':True}):
            self.assertEqual(d.verified_government_count('2026-11-04'),10)
        with patch.object(gov_verification,'verify_gov_publication',side_effect=RuntimeError('public mismatch')),patch('builtins.print'):
            self.assertIsNone(d.verified_government_count('2026-11-04'))
