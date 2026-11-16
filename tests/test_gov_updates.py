import json
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aidaily.ai_news import gov
from aidaily.integrations import gov as remote

class GovUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.public_patcher=patch.object(remote,'fetch_public',return_value={'status':'auth_required','reason_code':'credential_missing','checked_at':'2026-11-04T00:00:00Z','records':[]})
        self.public_mock=self.public_patcher.start();self.addCleanup(self.public_patcher.stop)
    def row(self,ident='PBLN_001',title='2026 AI 기술개발 지원사업',summary='AI 연구개발 지원'):
        return {'pblancId':ident,'pblancNm':title,'pblancUrl':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId='+ident,'jrsdInsttNm':'과학기술정보통신부','creatPnttm':'2026-11-03 10:00:00','reqstBeginEndDe':'20261101 ~ 20261109','bsnsSumryCn':summary,'private_extra':'do-not-publish'}
    def payload(self,rows):return {'source':'bizinfo','status':'ok','checked_at':'2026-11-04T00:00:00+00:00','response_sha256':'a'*64,'records':rows}
    def test_remote_one_get_and_key_never_in_artifact(self):
        path=Path(__file__).resolve().parents[1]/'operations/gov-remote/fetch.py'
        spec=importlib.util.spec_from_file_location('test_gov_fetch',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        key='sample-private-key-123';response={'jsonArray':{'item':[self.row(summary='안내 '+key)]}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(response,ensure_ascii=False).encode()
        class Opener:
            def __init__(self):self.calls=0
            def open(self,*args,**kwargs):self.calls+=1;return Response()
        opener=Opener();previous=os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                with patch.dict(os.environ,{'BIZINFO_API_KEY':key}),patch.object(mod.urllib.request,'build_opener',return_value=opener):mod.main()
                text=Path('gov-snapshot.json').read_text();self.assertNotIn(key,text);self.assertNotIn('private_extra',text);self.assertEqual(opener.calls,1)
            finally:os.chdir(previous)
    def test_duplicate_run_name_is_not_downloaded_or_redispatched(self):
        listing=json.dumps([{'displayTitle':'AIDAILY006-gov-test','databaseId':1,'status':'completed'}, {'displayTitle':'AIDAILY006-gov-test','databaseId':2,'status':'completed'}])
        with patch.object(remote,'_gh',return_value=listing) as call:
            with self.assertRaisesRegex(remote.Failed,'duplicate_request_id'):remote.lookup('gov-test')
            call.assert_called_once()

    def test_rejects_mismatched_duplicate_untrusted_and_missing_links(self):
        original=self.row()
        self.assertIsNotNone(gov._normal(original))
        for link in [
            'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_002',
            original['pblancUrl']+'&pblancId=PBLN_001',
            original['pblancUrl']+'&serviceKey=secret',
            'https://www.bizinfo.go.kr/other?pblancId=PBLN_001',
            'http://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_001',
            '',
        ]:
            with self.subTest(link=link):self.assertIsNone(gov._normal({**original,'pblancUrl':link}))


    def test_public_api_auth_error_is_preserved_without_key_exposure(self):
        self.public_patcher.stop()
        import urllib.request
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'<response><header><resultCode>30</resultCode></header></response>'
        class Opener:
            calls=0
            def open(self,*args,**kwargs):self.calls+=1;return Response()
        opener=Opener()
        with patch.object(remote,'_public_key',return_value='private-demo-key'),patch.object(urllib.request,'build_opener',return_value=opener):
            result=remote.fetch_public('msit','2026-11-04')
        self.assertEqual(result['status'],'auth_required');self.assertNotIn('private-demo-key',json.dumps(result));self.assertEqual(opener.calls,1)


    def test_public_identifier_parameters_require_numeric_values(self):
        msit={'subject':'AI 기술개발','viewUrl':'https://www.msit.go.kr/bbs/view.do?sCode=user&mId=311&mPid=121&bbsSeqNo=100&nttSeqNo=123'}
        self.assertIsNotNone(gov._public_normal('msit',msit))
        for old,new in [('sCode=user','sCode=admin'),('mId=311','mId=abc'),('mPid=121','mPid=x'),('bbsSeqNo=100','bbsSeqNo=x'),('nttSeqNo=123','nttSeqNo=x')]:
            self.assertIsNone(gov._public_normal('msit',{**msit,'viewUrl':msit['viewUrl'].replace(old,new)}))
        bid={'bidNtceNm':'AI 개발','bidNtceDtlUrl':'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=202601&bidPbancOrd=ab','bidNtceNo':'202601','bidNtceOrd':'ab'}
        self.assertIsNone(gov._public_normal('koneps',bid))

    def test_public_detail_url_identity_is_checked(self):
        row={'bidNtceNm':'AI 개발','bidNtceDtlUrl':'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=202601&bidPbancOrd=00','bidNtceNo':'202601','bidNtceOrd':'00'}
        self.assertIsNotNone(gov._public_normal('koneps',row))
        self.assertIsNone(gov._public_normal('koneps',{**row,'bidNtceOrd':'01'}))
        self.assertIsNone(gov._public_normal('koneps',{**row,'bidNtceDtlUrl':row['bidNtceDtlUrl']+'&key=x'}))


    def test_topic_rank_prefers_gpu_and_places_cancellation_last(self):
        rows=[{'title':'서울 뉴미디어 운영','summary':'','published_date':'2026-11-04'}, {'title':'교육 연구용 GPU 클라우드 도입','summary':'','published_date':'2026-11-01'}, {'title':'AI 기술개발 공고 취소','summary':'','published_date':'2026-11-04'}]
        gov._rank(rows)
        self.assertEqual([x['title'] for x in rows],['교육 연구용 GPU 클라우드 도입','서울 뉴미디어 운영','AI 기술개발 공고 취소'])



class GovPublicIdentifierBoundaryTests(unittest.TestCase):
    row=GovUpdatesTest.row
    def test_collection_and_public_url_reject_same_oversized_ids(self):
        from aidaily.publishing.gov_section import public_url
        for source,row in [('msit',{'subject':'AI 과제','viewUrl':'https://www.msit.go.kr/bbs/view.do?sCode=user&mId=311&mPid=121&bbsSeqNo=100&nttSeqNo='+('1'*25)}),('koneps',{'bidNtceNm':'AI 용역','bidNtceNo':'R26BK123','bidNtceOrd':'1'*11,'bidNtceDtlUrl':'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK123&bidPbancOrd='+('1'*11)})]:
            self.assertIsNone(gov._public_normal(source,row))
            self.assertEqual(public_url(row.get('viewUrl')or row['bidNtceDtlUrl'],notice=True),'')

    def test_local_three_source_first_edition_no_remote_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row=self.row();row['creatPnttm']='2026-11-04 09:42:27'
            def fetch(source,date,keyword):
                return {'status':'ok','records':[row] if source=='bizinfo' else [],'checked_at':'2026-11-04T00:45:00Z','reason_code':None,'response_sha256':'a'*64}
            with patch.object(remote,'KEYWORDS',('one',)),patch.object(remote,'fetch_public',side_effect=fetch) as calls,patch.object(remote,'dispatch') as dispatch,patch.object(remote,'lookup') as lookup:
                out=gov.run('2026-11-04',root=root);self.assertEqual(out['status'],'complete');self.assertEqual(out['selection_revision'],3)
                self.assertEqual(out['items'][0]['published_at'],'2026-11-04 09:42:27');self.assertEqual(out['items'][0]['published_date'],'2026-11-04')
                self.assertTrue(all(x['origin']=='mini1_https' for x in out['sources']))
                self.assertEqual(out,gov.run('2026-11-04',root=root));self.assertEqual(calls.call_count,3);dispatch.assert_not_called();lookup.assert_not_called()

    def test_legacy_uncertain_dispatch_is_preserved_and_never_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'runs').mkdir();state={'status':'pending','request_id':'old-uncertain'}
            p=root/'runs/2026-11-04.json';p.write_text(json.dumps(state))
            with patch.object(remote,'fetch_public') as fetch,patch.object(remote,'dispatch') as dispatch,patch.object(remote,'lookup') as lookup:
                with self.assertRaisesRegex(RuntimeError,'previous_submission_uncertain'):gov.run('2026-11-04',root=root)
                fetch.assert_not_called();dispatch.assert_not_called();lookup.assert_not_called();self.assertEqual(json.loads(p.read_text()),state)

    def test_local_biz_auth_failure_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(remote,'KEYWORDS',('one',)),patch.object(remote,'fetch_public',return_value={'status':'auth_required','records':[],'reason_code':'api_rejected','checked_at':'2026-11-04T00:00:00Z'}) as fetch:
                a=gov.run('2026-11-04',root=root);b=gov.run('2026-11-04',root=root)
                self.assertEqual(a['sources'][0]['status'],'auth_required');self.assertEqual(b['sources'][0]['status'],'auth_required')
                self.assertEqual(sum(c.args[0]=='bizinfo' for c in fetch.call_args_list),1)

    def test_legacy_three_source_edition_gets_local_biz_without_repeating_other_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'runs').mkdir();(root/'private').mkdir();(root/'editions').mkdir()
            old={'date':'2026-11-04','status':'complete','selection_revision':2,'checked_at':'2026-11-04T00:00:00Z','items':[{'title':'old'}],'sources':[{'id':i,'status':'ok'} for i in ('bizinfo','msit','koneps')]}
            (root/'editions/2026-11-04.json').write_text(json.dumps(old));(root/'runs/2026-11-04.json').write_text('{"status":"complete"}')
            (root/'private/2026-11-04-msit-00.json').write_text(json.dumps({'status':'ok','records':[],'checked_at':'2026-11-04T00:00:00Z'}))
            (root/'private/2026-11-04-koneps-00.json').write_text(json.dumps({'status':'ok','records':[],'checked_at':'2026-11-04T00:00:00Z'}))
            response={'status':'ok','records':[self.row()],'reason_code':None,'checked_at':'2026-11-04T00:01:00Z','response_sha256':'a'*64}
            with patch.object(remote,'KEYWORDS',('one',)),patch.object(remote,'fetch_public',return_value=response) as fetch,patch.object(remote,'dispatch') as dispatch,patch.object(remote,'lookup') as lookup:
                result=gov.run('2026-11-04',root=root)
                self.assertEqual(result['selection_revision'],3);fetch.assert_called_once_with('bizinfo','2026-11-04',None);dispatch.assert_not_called();lookup.assert_not_called()
                self.assertEqual(json.loads((root/'editions/2026-11-04.before-mini1-direct.json').read_text()),old)

    def test_biz_local_one_get_and_no_key_in_snapshot(self):
        import urllib.request
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'jsonArray':{'item':[self_test.row(summary='AI 개발 key-secret-xyz')]}},ensure_ascii=False).encode()
        class Opener:
            calls=0
            def open(self,*args,**kwargs):self.calls+=1;return Response()
        self_test=self;opener=Opener()
        with patch.object(remote,'_biz_key',return_value='key-secret-xyz'),patch.object(urllib.request,'build_opener',return_value=opener):
            result=remote.fetch_public('bizinfo','2026-11-04')
        self.assertEqual(opener.calls,1);self.assertEqual(result['status'],'ok');self.assertNotIn('key-secret-xyz',json.dumps(result));self.assertEqual(len(result['response_sha256']),64)

    def test_timestamp_migration_does_not_create_false_change(self):
        item=gov._normal(self.row());old=dict(item);old.pop('published_at')
        self.assertEqual(gov._hash(old),gov._hash(item))
        msit={'subject':'AI 기술개발','viewUrl':'https://www.msit.go.kr/bbs/view.do?sCode=user&mId=311&mPid=121&bbsSeqNo=100&nttSeqNo=123','pressDt':'2026-11-04'}
        self.assertEqual(gov._public_normal('msit',msit)['published_at'],'2026-11-04')
        bid={'bidNtceNm':'AI 개발','bidNtceDtlUrl':'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=202601&bidPbancOrd=00','bidNtceNo':'202601','bidNtceOrd':'00','bidNtceDt':'2026-11-04 09:10:22'}
        self.assertEqual(gov._public_normal('koneps',bid)['published_at'],'2026-11-04 09:10:22')

if __name__=='__main__':unittest.main()
