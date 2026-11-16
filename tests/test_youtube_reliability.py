import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.integrations import youtube_transcript as t, openrouter
from aidaily.youtube_summaries import pipeline

class TranscriptRecovery(unittest.TestCase):
    def test_downloaded_audio_and_derivatives_are_deleted_on_success_and_failure(self):
        for fail in (False, True):
            created = []
            def downloaded(url, lang, root):
                created.append(Path(root))
                for name in ('audio.m4a', 'asr16k.wav', 'audio.srt'):
                    Path(root, name).write_text('temporary')
                if fail:
                    raise RuntimeError('whisper_process_failed')
                return ([{'start': 0, 'text': 'x' * 1000}], 'asr')
            with self.subTest(fail=fail), patch.object(t, '_yt_subs', return_value=None), patch.object(t, '_yt_asr', side_effect=downloaded):
                result = t.transcribe('fixture')
                self.assertEqual('error' in result, fail)
                self.assertEqual(len(created), 1)
                self.assertFalse(created[0].exists())

    def test_short_captions_and_timeout_recover_with_asr(self):
        for caption in [([{'start':0,'text':'x'*999}], 'subs'), subprocess.TimeoutExpired('fixture',120)]:
            with self.subTest(caption=type(caption).__name__), patch.object(t,'_yt_subs',side_effect=caption if isinstance(caption,Exception) else None,return_value=caption), patch.object(t,'_yt_asr',return_value=([{'start':0,'text':'speech '*200}], 'asr')) as asr:
                result=t.transcribe('fixture')
                self.assertEqual(result['source'],'asr');asr.assert_called_once()
                self.assertEqual(result['stages'][-1]['status'],'ok')

    def test_1000_chars_does_not_download_audio(self):
        with patch.object(t,'_yt_subs',return_value=([{'start':0,'text':'x'*1000}],'subs')), patch.object(t,'_yt_asr') as asr:
            self.assertEqual(t.transcribe('fixture')['char_count'],1000);asr.assert_not_called()

    def test_download_failure_is_visible_and_does_not_invoke_whisper(self):
        with tempfile.TemporaryDirectory() as root, patch.object(t.subprocess,'run',return_value=subprocess.CompletedProcess([],1)), patch.object(t,'_asr') as asr:
            Path(root,'audio.m4a.part').write_text('partial')
            with self.assertRaisesRegex(RuntimeError,'audio_download_failed'): t._yt_asr('fixture','ko',root)
            asr.assert_not_called()

    def test_failed_whisper_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as root, patch.object(t.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
            Path(root,'old.srt').write_text('old')
            with self.assertRaisesRegex(RuntimeError,'whisper_process_failed'):t._whisper('fixture','ko',root)

    def test_all_paths_fail_with_diagnostics(self):
        with patch.object(t,'_yt_subs',return_value=None),patch.object(t,'_yt_asr',side_effect=RuntimeError('audio_download_failed')):
            result=t.transcribe('fixture');self.assertIn('error',result)
            self.assertEqual(result['stages'][-1]['reason'],'audio_download_failed')

class BatchRecovery(unittest.TestCase):
    def test_blocked_video_does_not_abort_valid_reports(self):
        videos=[{'video_id':'blocked','title':'blocked'},{'video_id':'good','title':'good'}]
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=videos),patch.object(pipeline,'process_video',side_effect=[openrouter.RoutingBlocked('review'),('good-report',{'text':'ok'})]):
            result=pipeline.run([],root,10)
            self.assertEqual(result['done_ids'],['good']);self.assertEqual(len(result['failures']),1)
            self.assertEqual(json.loads(Path(root,'run-status.json').read_text())['failures'][0]['state'],'review_or_pending')
            self.assertIn('good-report',json.loads(Path(root,pipeline.QUEUE_NAME).read_text())['messages'])

class AdditionalStageChecks(unittest.TestCase):
    def test_failed_conversion_does_not_accept_partial_wav(self):
        with tempfile.TemporaryDirectory() as root, patch.object(t.subprocess, 'run', return_value=subprocess.CompletedProcess([],1)):
            Path(root,'asr16k.wav').write_bytes(b'partial')
            self.assertIsNone(t._to_16k_wav('fixture',root))

    def test_metadata_timeout_is_isolated(self):
        with tempfile.TemporaryDirectory() as root, patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'video_metadata',side_effect=[subprocess.TimeoutExpired('fixture',60),{}]),patch.object(pipeline,'process_video',return_value=('good',{})):
            result=pipeline.run(['https://youtu.be/abcdefghijk','https://youtu.be/lmnopqrstuv'],root,10)
            self.assertEqual(result['done_ids'],['lmnopqrstuv'])
            self.assertEqual(result['failures'][0]['stage'],'metadata')

class PublicationManifest(unittest.TestCase):
    def test_only_current_validated_report_is_copied(self):
        from aidaily.publishing import youtube_summaries as publisher
        def git(args, **kwargs):
            if args[1]=='clone': Path(args[-1]).mkdir()
            return subprocess.CompletedProcess(args,0,stdout='fixture-remote')
        observed=[]
        def commit(root,*args,**kwargs):
            observed.extend(p.name for p in root.glob('*.html'));return True
        with tempfile.TemporaryDirectory() as root,patch.object(publisher.subprocess,'run',side_effect=git),patch.object(publisher,'commit_and_push',side_effect=commit),patch.object(publisher,'_update_processed_log') as processed:
            Path(root,'good.html').write_text('validated');Path(root,'stale.html').write_text('stale')
            publisher.publish(root,'2026-10-11',{'good':{}},['fixture'],dry_run=True)
            self.assertEqual(observed,['good.html']);processed.assert_not_called()

class DurableBatchRecovery(unittest.TestCase):
    def test_valid_staged_report_is_resumed_without_generation(self):
        import time, hashlib
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[{'video_id':'good'}]),patch.object(pipeline,'process_video') as generate:
            Path(root,'good-report.html').write_text('validated')
            Path(root,pipeline.QUEUE_NAME).write_text(json.dumps({'date':time.strftime('%Y-%m-%d'),'messages':{'good-report':{}}}))
            Path(root,'processed_video_ids.json').write_text(json.dumps(['good']))
            Path(root,'run-status.json').write_text(json.dumps({'date':time.strftime('%Y-%m-%d'),'queue':{'good-report':{}},'done_ids':['good'],'report_hashes':{'good-report':hashlib.sha256(b'validated').hexdigest()}}))
            result=pipeline.run([],root,10)
            self.assertEqual(result['done_ids'],['good']);generate.assert_not_called()

class IntegrityRecovery(unittest.TestCase):
    def test_modified_staged_report_is_not_resumed(self):
        import hashlib,time
        with tempfile.TemporaryDirectory() as root,patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[{'video_id':'good','title':'fixture'}]),patch.object(pipeline,'process_video',side_effect=RuntimeError('fixture')) as generate:
            Path(root,'good-report.html').write_text('modified')
            Path(root,'run-status.json').write_text(json.dumps({'date':time.strftime('%Y-%m-%d'),'queue':{'good-report':{}},'done_ids':['good'],'report_hashes':{'good-report':hashlib.sha256(b'validated').hexdigest()}}))
            result=pipeline.run([],root,10)
            self.assertEqual(result['queue'],{});generate.assert_called_once()

    def test_concurrent_run_does_not_touch_staging(self):
        import fcntl
        with tempfile.TemporaryDirectory() as root,Path(root,'run.lock').open('a') as lock,patch.object(pipeline,'_run') as execute:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):pipeline.run([],root,10)
            execute.assert_not_called()

class CrossDayRecovery(unittest.TestCase):
    def test_retryable_previous_day_is_carried_beyond_rss_window(self):
        with tempfile.TemporaryDirectory() as root:
            previous=Path(root,'2026-10-01');previous.mkdir()
            video={'video_id':'retry','title':'fixture','url':'https://example.invalid','channel':'fixture'}
            Path(previous,'run-status.json').write_text(json.dumps({'done_ids':[],'failures':[{'state':'retryable','video':video}]}))
            current=str(Path(root,'2026-10-11'))
            with patch.object(pipeline,'DEFAULT_STAGING',current),patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[]),patch.object(pipeline,'process_video',return_value=('retried',{})) as process:
                result=pipeline.run([],current,10)
                self.assertEqual(result['done_ids'],['retry']);self.assertEqual(process.call_args.args[0],video)

class RetryStatePrecedence(unittest.TestCase):
    def test_new_review_state_supersedes_old_retry(self):
        with tempfile.TemporaryDirectory() as root:
            video={'video_id':'fixture','title':'fixture','url':'https://example.invalid'}
            for date,state in [('2026-10-01','retryable'),('2026-10-02','review_or_pending')]:
                folder=Path(root,date);folder.mkdir()
                Path(folder,'run-status.json').write_text(json.dumps({'done_ids':[],'failures':[{'video_id':'fixture','state':state,'video':video}]}))
            current=str(Path(root,'2026-10-11'))
            with patch.object(pipeline,'DEFAULT_STAGING',current),patch.object(pipeline,'load_processed_ids',return_value=set()),patch.object(pipeline,'load_config',return_value={}),patch.object(pipeline,'collect_targets',return_value=[]),patch.object(pipeline,'process_video') as process:
                result=pipeline.run([],current,10)
                self.assertEqual(result['target_count'],0);process.assert_not_called()
