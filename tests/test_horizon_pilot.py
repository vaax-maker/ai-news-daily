import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.ai_news import horizon
from aidaily.integrations import horizon as sources, openrouter


class HorizonPilotTest(unittest.TestCase):
    def test_source_lookback_and_explicit_status(self):
        now=dt.datetime(2026,11,3,12,tzinfo=dt.timezone.utc)
        data={'hits':[{'objectID':'1','url':'https://example.org/new','title':'AI news','created_at':'2026-11-01T00:00:00Z'}, {'objectID':'2','url':'https://example.org/old','title':'old','created_at':'2026-10-30T00:00:00Z'}]}
        source={'id':'hn','name':'HN','type':'hackernews','url':'https://example.org/feed'}
        info,items=sources.collect(source,now=now,lookback_hours=72,fetch=lambda *a,**k:(json.dumps(data).encode(),{}))
        self.assertEqual(len(items),1);self.assertEqual(info['lookback_hours'],72)
        info,items=sources.collect(source,now=now,lookback_hours=24,fetch=lambda *a,**k:(json.dumps(data).encode(),{}))
        self.assertEqual(items,[]);self.assertIsNone(info['newest_published_at']);self.assertEqual(info['status'],'ok');self.assertEqual(info['candidate_count'],0)
        info,items=sources.collect(source,now=now,fetch=lambda *a,**k:(_ for _ in ()).throw(OSError()))
        self.assertEqual(info['status'],'unavailable');self.assertEqual(info['candidate_count'],0)

    def test_real_engine_resume_pending_without_recollection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'upstream').symlink_to(horizon.ROOT/'upstream',target_is_directory=True);shutil.copytree(horizon.ROOT/'profiles',root/'profiles')
            (root/'settings.json').write_text(json.dumps({'pilot':{'start':'2026-11-03','end':'2026-11-09'},'candidate_limit':20,'selected_limit':4,'minimum_score':6,'per_source_limit':8,'sources':[{'id':'x'}]}))
            item={'id':'x:1','title':'AI framework release','url':'https://example.org/a','source_name':'Example','source_type':'rss','published_at':'2026-11-03T00:00:00+00:00','content':'AI framework release with new feature.'}
            receipt={'id':'x','name':'Example','type':'rss','url':'https://example.org/feed','status':'ok','candidate_count':1}
            def answer(system,user,**kwargs):
                if 'Tool results' in user:
                    return json.dumps({'title':'AI 도구 출시','blocks':[{'id':'summary','type':'section','title':'핵심','content':'새 기능이 출시됐다. 개발자가 사용할 수 있다.','source_refs':[]}]},ensure_ascii=False)
                return json.dumps({'score':8,'reason':'실용적 기능','summary':'새 도구','tags':['AI']},ensure_ascii=False)
            with patch.object(horizon,'ROOT',root),patch.object(horizon,'_existing',return_value=[]),patch.object(sources,'collect',return_value=(receipt,[item])) as collect,patch.object(sources,'fetch_original',return_value='Verified source body. '*30),patch.object(openrouter,'complete',side_effect=openrouter.CompletionPending('test-request')):
                with self.assertRaises(Exception):horizon.run('2026-11-03',root=root)
                state=json.loads((root/'runs/2026-11-03.json').read_text());self.assertEqual(state['status'],'pending');self.assertEqual(state['pending']['request_id'],'test-request');self.assertEqual(state['analyzed'],{})
                self.assertFalse((root/'editions/2026-11-03.json').exists())
                profile=root/'profiles/tech-news/analysis.md'; original=profile.read_text();profile.write_text(original+' changed')
                with self.assertRaisesRegex(RuntimeError,'contract'):horizon.run('2026-11-03',root=root)
                profile.write_text(original)
                with patch.object(openrouter,'complete',side_effect=answer):result=horizon.run('2026-11-03',root=root)
                self.assertEqual(collect.call_count,1);self.assertEqual(result['metrics']['selected_count'],1);self.assertEqual(result['items'][0]['source_name'],'Example')
                final=json.loads((root/'runs/2026-11-03.json').read_text());self.assertEqual(final['originals']['x:1']['status'],'ok');self.assertTrue(final['originals']['x:1']['sha256'])

    def test_collection_failure_recovers_without_losing_receipt_or_old_edition(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'upstream').symlink_to(horizon.ROOT/'upstream',target_is_directory=True);shutil.copytree(horizon.ROOT/'profiles',root/'profiles')
            (root/'settings.json').write_text(json.dumps({'pilot':{'start':'2026-11-03','end':'2026-11-09'},'candidate_limit':20,'selected_limit':4,'minimum_score':6,'per_source_limit':8,'sources':[{'id':'x'}]}))
            (root/'editions').mkdir();edition=root/'editions/2026-11-03.json';edition.write_text('{"old":true}')
            bad={'id':'x','status':'unavailable','candidate_count':0,'error_type':'URLError'}
            good={'id':'x','name':'Example','type':'rss','url':'https://example.org/feed','status':'ok','candidate_count':1}
            item={'id':'x:1','title':'AI release','url':'https://example.org/a','source_name':'Example','source_type':'rss','published_at':'2026-11-03T00:00:00+00:00','content':'AI release with new feature.'}
            def answer(system,user,**kwargs):
                if 'Tool results' in user:return json.dumps({'title':'출시','blocks':[{'id':'summary','type':'section','title':'핵심','content':'새 기능이 출시됐다. 개발자가 사용할 수 있다.','source_refs':[]}]},ensure_ascii=False)
                return json.dumps({'score':8,'reason':'실용적','summary':'새 도구','tags':[]},ensure_ascii=False)
            with patch.object(horizon,'ROOT',root),patch.object(horizon,'_existing',return_value=[]),patch.object(sources,'collect',side_effect=[(bad,[]),(good,[item])]) as collect,patch.object(sources,'fetch_original',return_value='Verified source body. '*30),patch.object(openrouter,'complete',side_effect=answer) as model:
                with self.assertRaisesRegex(RuntimeError,'unavailable'):horizon.run('2026-11-03',root=root)
                self.assertEqual(model.call_count,0);self.assertEqual(json.loads(edition.read_text()),{'old':True})
                result=horizon.run('2026-11-03',root=root)
                self.assertEqual(result['status'],'complete');self.assertEqual(model.call_count,2);self.assertEqual(collect.call_count,2)
                archived=json.loads((root/'runs/2026-11-03.collection-failure-0001.json').read_text())
                self.assertEqual(archived['sources'],[bad])
                self.assertEqual(horizon.run('2026-11-03',root=root),result)
                self.assertEqual(model.call_count,2);self.assertEqual(collect.call_count,2)

    def test_collection_failure_with_pending_work_is_never_reset(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'upstream').symlink_to(horizon.ROOT/'upstream',target_is_directory=True);shutil.copytree(horizon.ROOT/'profiles',root/'profiles')
            (root/'settings.json').write_text(json.dumps({'pilot':{'start':'2026-11-03','end':'2026-11-09'}}))
            (root/'runs').mkdir();state={'status':'collection_unavailable','pending':{'request_id':'keep'}}
            (root/'runs/2026-11-03.json').write_text(json.dumps(state))
            with patch.object(horizon,'ROOT',root),patch.object(sources,'collect') as collect,patch.object(openrouter,'complete') as model:
                with self.assertRaisesRegex(RuntimeError,'work attached'):horizon.run('2026-11-03',root=root)
                collect.assert_not_called();model.assert_not_called()
                self.assertEqual(json.loads((root/'runs/2026-11-03.json').read_text()),state)

    def test_release_feed_preserves_prerelease_tag(self):
        source={'id':'g','name':'GitHub','type':'github','url':'https://example.org/feed'}
        feed=b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>x</title><id>x</id><updated>2026-11-03T10:00:00Z</updated><entry><title>v0.33.0</title><id>x</id><link href="https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3"/><updated>2026-11-03T10:00:00Z</updated></entry></feed>"""
        _,items=sources.collect(source,now=dt.datetime(2026,11,3,12,tzinfo=dt.timezone.utc),fetch=lambda *a,**k:(feed,{}))
        self.assertEqual(items[0]['title'],'v0.33.0rc3')

    def test_attribution_uses_submission_timestamp_and_exact_release_tag(self):
        title,meta=horizon._item_attribution({'source_type':'hackernews','url':'https://www.example.org/story'},'Article')
        self.assertEqual(meta['published_at_note'],'Hacker News 게시 시각')
        self.assertEqual(meta['publisher_hostname'],'example.org')
        self.assertEqual(title,'Article')
        title,meta=horizon._item_attribution({'source_type':'github','url':'https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3'},'v0.33.0 업데이트')
        self.assertIn('v0.33.0rc3',title)
        self.assertEqual(meta['release_tag'],'v0.33.0rc3')
        self.assertNotIn('prerelease',meta)
        unchanged,_=horizon._item_attribution({'source_type':'github','url':'https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3'},title)
        self.assertEqual(unchanged,title)

    def test_original_fetch_rejects_private_initial_and_redirect(self):
        import httpx
        horizon._load_engine()  # Add pinned Horizon source to the module path.
        from src import url_security
        with self.assertRaises(url_security.UnsafeURLError):
            sources.fetch_original('https://127.0.0.1/private')
        requests=[]
        def response(request):
            requests.append(str(request.url))
            return httpx.Response(302,headers={'location':'https://127.0.0.1/private'},request=request)
        client=httpx.AsyncClient(transport=httpx.MockTransport(response),trust_env=False)
        async def resolve(host,port):
            return {'127.0.0.1'} if host=='127.0.0.1' else {'8.8.8.8'}
        with patch.object(httpx,'AsyncClient',return_value=client),patch.object(url_security,'_resolve_hostname',side_effect=resolve):
            with self.assertRaises(url_security.UnsafeURLError):
                sources.fetch_original('https://public.example/article')
        self.assertEqual(requests,['https://public.example/article'])

    def test_original_title_only_is_not_substantive(self):
        html=b'<html><head><title>AI release</title></head><body><h1>AI release</h1></body></html>'
        self.assertEqual(sources.fetch_original('https://example.org/story',fetch=lambda *a,**k:(html,{})),'')

    def test_overlap_history_only_uses_prior_published_editions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);docs=root/'docs';docs.mkdir()
            (docs/'search-index.json').write_text(json.dumps([{'url':'https://example.org/aidaily','title':'Daily item'}]))
            history=[{'date':'2026-11-03','status':'published','items':[{'id':'1','title':'Published story','url':'https://example.org/published'}]},
                     {'date':'2026-11-03','status':'generated','items':[{'id':'2','title':'Unpublished story','url':'https://example.org/generated'}]},
                     {'date':'2026-11-04','status':'published','items':[{'url':'https://example.org/today','title':'Today'}]}]
            (root/'published-history.json').write_text(json.dumps(history))
            with patch.object(horizon,'ROOT',root),patch.object(horizon.config,'DOCS_ROOT',docs):
                rows=horizon._existing('2026-11-04');key=lambda x:x.split('?')[0]
                self.assertTrue(horizon._overlap({'url':'https://example.org/published?ref=1','title':'different'},rows,key))
                self.assertTrue(horizon._overlap({'url':'https://example.org/aidaily','title':'different'},rows,key))
                self.assertFalse(horizon._overlap({'url':'https://example.org/generated','title':'different'},rows,key))
                self.assertFalse(horizon._overlap({'url':'https://example.org/today','title':'different'},rows,key))
                (root/'published-history.json').write_text('{broken')
                rows=horizon._existing('2026-11-04')
                self.assertEqual(rows,[{'url':'https://example.org/aidaily','title':'Daily item'}])

    def test_rank_diversity(self):
        rows=[{'id':str(i),'source_name':'A' if i<3 else 'B','score':10-i} for i in range(5)]
        self.assertEqual([x['id'] for x in horizon._select(rows,4,6)],['0','1','3','4'])

if __name__=='__main__':unittest.main()
