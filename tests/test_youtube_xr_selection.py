import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.youtube_summaries import pipeline, selection
from aidaily.integrations.openrouter import CompletionPending

class XRSelectionTest(unittest.TestCase):
    def test_pin_first_xr_without_video_id_preserves_relative_order(self):
        rows=[{'title':'AI 1'}, {'title':'VR headset'}, {'title':'AI 2'}, {'title':'XR news'}]
        pinned=selection.pin_first_xr(rows)
        self.assertEqual([x['title'] for x in pinned],['VR headset','AI 1','AI 2','XR news'])
        self.assertEqual([x['title'] for x in rows],['AI 1','VR headset','AI 2','XR news'])
        self.assertEqual(selection.pin_first_xr([{'title':'AI only'}]),[{'title':'AI only'}])

    def test_conservative_evidence(self):
        for title in ('Steam Frame Stream Stuttering? Check Your USB Ports','Meta VR Glasses vs XREAL AURA','Quest 3 headset review','가상현실 기술 전망'):
            self.assertTrue(selection.is_xr({'title':title}),title)
        for title in ('Quest for the best AI model','AI glasses launch','AI agent tutorial','Virtual assistant setup'):
            self.assertFalse(selection.is_xr({'title':title}),title)
        self.assertFalse(selection.is_xr({'title':'weekly news','channel':'UploadVR'}))
        self.assertTrue(selection.is_xr({'source_title':'VR headset review','title':'새 제품 리뷰'}))
        self.assertFalse(selection.is_xr({'source_title':'일반 AI 영상','title':'VR headset'}))

    def test_xr_precedes_cap_and_14_day_fallback_respects_dedup_duration(self):
        now=dt.datetime.now(dt.timezone.utc)
        entries={'general':[{'video_id':f'general{i:04d}','title':'AI news','published':now-dt.timedelta(hours=3)} for i in range(12)],
                 'vr':[{'video_id':'oldvr000001','title':'VR headset news','published':now-dt.timedelta(days=5)}, {'video_id':'tooold00001','title':'XR goggles','published':now-dt.timedelta(days=15)}]}
        cfg={'hours':48,'min_duration':240,'channels':[{'channel_id':'general','handle':'A'},{'channel_id':'vr','handle':'B'}]}
        with patch.object(pipeline,'fetch_channel',side_effect=lambda cid:entries[cid]) as fetch,patch.object(pipeline,'duration_seconds',return_value=600):
            chosen=pipeline.collect_targets(cfg,set(),10)
            self.assertEqual(len(chosen),10);self.assertEqual(chosen[0]['video_id'],'oldvr000001');self.assertEqual(fetch.call_count,2)
            no_xr=pipeline.collect_targets(cfg,{'oldvr000001'},10)
            self.assertFalse(any(selection.is_xr(v) for v in no_xr));self.assertEqual(len(no_xr),10)
        with patch.object(pipeline,'fetch_channel',side_effect=lambda cid:entries[cid]),patch.object(pipeline,'duration_seconds',side_effect=lambda vid:100 if vid=='oldvr000001' else 600):
            self.assertFalse(any(selection.is_xr(v) for v in pipeline.collect_targets(cfg,set(),10)))

    def test_xr_window_never_exceeds_fourteen_days_even_when_config_larger(self):
        now=dt.datetime.now(dt.timezone.utc);old={'video_id':'oldold00001','title':'VR headset review','published':now-dt.timedelta(days=15)}
        cfg={'hours':500,'channels':[{'channel_id':'xr','handle':'XR'}]}
        with patch.object(pipeline,'fetch_channel',return_value=[old]),patch.object(pipeline,'duration_seconds',return_value=600):
            self.assertEqual(pipeline.collect_targets(cfg,set(),10),[])

    def test_failed_first_xr_uses_distinct_backup_and_keeps_10_limit(self):
        videos=[{'video_id':'xr000000001','title':'VR headset'},{'video_id':'xr000000002','title':'XR headset','_xr_alternate':True},{'video_id':'xr000000003','title':'VR device','_xr_alternate':True}]+[{'video_id':f'ai{i:09d}','title':'AI news'} for i in range(9)]
        attempted=[]
        def process(v,root,date):
            attempted.append(v['video_id'])
            if v['video_id']=='xr000000001':raise ValueError('failed')
            slug=v['video_id'];Path(root,slug+'.html').write_text('ok');return slug,{'text':'ok'}
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=videos),patch.object(pipeline,'process_video',side_effect=process):
            result=pipeline.run([],root,10)
        self.assertEqual(len(result['queue']),10);self.assertEqual(result['target_count'],10);self.assertEqual(result['xr_done_ids'],['xr000000002'])
        self.assertNotIn('xr000000003',attempted);self.assertEqual(attempted.count('xr000000001'),1)

    def test_pending_xr_is_not_resubmitted_on_same_day_resume(self):
        videos=[{'video_id':'xr000000001','title':'VR headset'}, {'video_id':'xr000000002','title':'XR headset','_xr_alternate':True}]
        attempted=[]
        def process(v,root,date):
            attempted.append(v['video_id'])
            if v['video_id']=='xr000000001':raise CompletionPending('stable')
            Path(root,'xr.html').write_text('ok');return 'xr',{'text':'ok'}
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=videos),patch.object(pipeline,'process_video',side_effect=process):
            first=pipeline.run([],root,10);second=pipeline.run([],root,10)
        self.assertEqual(attempted.count('xr000000001'),1);self.assertEqual(attempted.count('xr000000002'),1)
        self.assertEqual(first['xr_done_ids'],['xr000000002']);self.assertEqual(second['xr_done_ids'],['xr000000002'])
        self.assertTrue(any(f['state']=='review_or_pending' for f in second['failures']))

    def test_failed_xr_remains_diagnostic_without_mandatory_quota(self):
        videos=[{'video_id':'xr000000001','title':'VR headset'},{'video_id':'ai000000001','title':'AI news'}]
        def process(v,root,date):
            if v['video_id'].startswith('xr'):raise ValueError('failure')
            Path(root,'good.html').write_text('html');return 'good',{'text':'ok'}
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=videos),patch.object(pipeline,'process_video',side_effect=process):
            result=pipeline.run([],root,10)
        self.assertEqual(len(result['queue']),1);self.assertFalse(result['xr_required']);self.assertFalse(result['xr_quality_passed']);self.assertEqual(result['xr_status'],'not_published')

    def test_cli_publishes_other_reports_when_xr_missing(self):
        result={'target_count':1,'queue':{'ok':{}},'xr_required':False,'xr_quality_passed':False,'staging_dir':'unused','date':'2026-11-04','done_ids':['id']}
        with patch.object(pipeline,'run',return_value=result),patch.object(pipeline,'publish') as publish,patch('sys.argv',['pipeline','--publish']):
            pipeline.main()
            publish.assert_called_once_with('unused','2026-11-04',{'ok':{}},['id'],dry_run=False)

    def test_daily_no_xr_candidate_generates_only_other_videos(self):
        videos=[{'video_id':'ai000000001','title':'AI news'}]
        def process(v,root,date):
            Path(root,'ai.html').write_text('html');return 'ai',{'text':'AI'}
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=videos),patch.object(pipeline,'process_video',side_effect=process):
            result=pipeline.run([],root,10)
            import json
            receipt=json.loads(Path(root,'run-status.json').read_text())
        self.assertEqual(result['done_ids'],['ai000000001'])
        self.assertEqual(result['xr_done_ids'],[])
        self.assertFalse(result['xr_required'])
        self.assertEqual(receipt['xr_policy'],'daily_14d_optional')
        self.assertEqual(receipt['xr_status'],'not_published')

    def test_old_xr_retry_does_not_bypass_daily_fourteen_day_window(self):
        import json
        with tempfile.TemporaryDirectory() as parent:
            current=Path(parent)/pipeline.time.strftime('%Y-%m-%d')
            previous=Path(parent)/'earlier';previous.mkdir()
            old={'video_id':'xr000000001','title':'VR headset','published_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=15)).isoformat()}
            (previous/'run-status.json').write_text(json.dumps({'failures':[{'state':'retryable','video':old}]}))
            video={'video_id':'ai000000001','title':'AI news'}
            attempted=[]
            def process(v,root,date):
                attempted.append(v['video_id']);Path(root,'ai.html').write_text('html');return 'ai',{'text':'AI'}
            with patch.object(pipeline,'DEFAULT_STAGING',str(current)),patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[video]),patch.object(pipeline,'process_video',side_effect=process):
                result=pipeline.run([],str(current),10)
        self.assertEqual(attempted,['ai000000001'])
        self.assertEqual(result['xr_done_ids'],[])

    def test_full_legacy_queue_preserves_successes_and_adds_one_xr(self):
        import hashlib,json
        with tempfile.TemporaryDirectory() as root:
            Path(root,'old.html').write_text('old')
            previous={'date':pipeline.time.strftime('%Y-%m-%d'),'done_ids':['old00000001'],
                      'queue':{'old':{'text':'preserved'}},
                      'report_hashes':{'old':hashlib.sha256(b'old').hexdigest()}}
            Path(root,'run-status.json').write_text(json.dumps(previous))
            def process(v,s,d):
                Path(s,'xr.html').write_text('xr');return 'xr',{'text':'XR'}
            with patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[{'video_id':'xr000000001','title':'VR headset'}]),patch.object(pipeline,'process_video',side_effect=process):
                result=pipeline.run([],root,1)
            self.assertTrue(result['xr_quality_passed'])
            self.assertEqual(result['queue']['old'],{'text':'preserved'})
            self.assertEqual(len(result['queue']),2)
            self.assertEqual(result['target_count'],2)
            self.assertEqual(json.loads(Path(root,'run-status.json').read_text())['target_count'],2)
            self.assertEqual(Path(root,'old.html').read_text(),'old')

    def test_explicit_url_is_exempt_from_daily_xr_requirement(self):
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'video_metadata',return_value={'video_id':'abcdefghijk','title':'AI news'}),patch.object(pipeline,'process_video',side_effect=lambda v,s,d:(Path(s,'good.html').write_text('ok') and ('good',{'text':'ok'}))):
            result=pipeline.run(['https://youtu.be/abcdefghijk'],root,10)
        self.assertFalse(result['xr_required']);self.assertTrue(result['xr_quality_passed'])

if __name__=='__main__':unittest.main()
