"""Local published-video state tests. No network, original Drive reads, or publishing."""
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings

from aidaily import config
from aidaily.youtube_summaries import processed_state as state, pipeline
from aidaily.publishing import youtube_summaries as publisher


class ProcessedVideoStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p=patch.object(config,'DATA_ROOT',self.root/'data');p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{},clear=True);p.start();self.addCleanup(p.stop)
        self.path=state.state_path()

    def seed(self, ids=('existing',)):
        return state.initialize(ids,sources=['local-fixture'])

    def test_default_reader_and_writer_share_local_path(self):
        self.seed()
        publisher._update_processed_log(['new'],publication_date='2026-11-02',slugs=['report'])
        self.assertEqual(pipeline.load_processed_ids(),{'existing','new'})
        self.assertEqual(self.path,(self.root/'data/youtube_summaries/processed-video-ids.json').resolve())
        self.assertTrue(self.path.is_file())

    def test_each_single_override_is_shared_and_conflicts_are_rejected(self):
        for key in ('YOUTUBE_SUMMARIES_STATE','YOUTUBE_SUMMARIES_PROCESSED_LOG'):
            with self.subTest(key=key),patch.dict(os.environ,{key:str(self.root/key)}):
                self.seed(['old'])
                publisher._update_processed_log(['new'],publication_date='2026-11-02')
                self.assertEqual(pipeline.load_processed_ids(),{'old','new'})
        with patch.dict(os.environ,{'YOUTUBE_SUMMARIES_STATE':str(self.root/'a'),'YOUTUBE_SUMMARIES_PROCESSED_LOG':str(self.root/'b')}):
            with self.assertRaises(state.ProcessedStateError):state.state_path()

    def test_cloud_paths_rejected_before_storage_access(self):
        for suffix in ('Library/CloudStorage/GoogleDrive-example/history.json','Google Drive/history.json'):
            with self.subTest(suffix=suffix),patch.dict(os.environ,{'YOUTUBE_SUMMARIES_STATE':str(self.root/suffix)}):
                with self.assertRaises(state.ProcessedStateError):state.state_path()
        self.assertFalse((self.root/'Library').exists())

    def test_migration_and_repeated_writes_preserve_more_than_500_ids(self):
        ids={f'old-{n}' for n in range(700)}
        self.seed(ids)
        state.initialize(['another'],sources=['fixture-two'])
        state.record_published(['new','new'],'2026-11-02')
        self.assertEqual(state.load_processed_ids(),ids|{'another','new'})
        self.assertEqual(json.loads(self.path.read_text())['total_processed'],702)

    def test_missing_or_corrupt_history_fails_closed(self):
        with self.assertRaises(state.ProcessedStateError):state.load_processed_ids()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        for content in ('{broken','[]','{}','{"processed_video_ids":[null]}'):
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaises(state.ProcessedStateError):state.load_processed_ids()
                with self.assertRaises(state.ProcessedStateError):state.record_published(['new'],'2026-11-02')

    def test_only_published_receipts_are_loaded(self):
        self.seed()
        receipts=state._receipt_dir(self.path);receipts.mkdir()
        (receipts/'published.json').write_text(json.dumps({'status':'published','processed_video_ids':['published']}))
        (receipts/'pending.json').write_text(json.dumps({'status':'pending','processed_video_ids':['pending']}))
        self.assertEqual(state.load_processed_ids(),{'existing','published'})

    def test_malformed_receipt_fails_closed_with_typed_error(self):
        self.seed()
        receipts=state._receipt_dir(self.path);receipts.mkdir()
        for content in ('{broken','[]','{"status":"published"}'):
            with self.subTest(content=content):
                (receipts/'broken.json').write_text(content)
                with self.assertRaises(state.ProcessedStateError):state.load_processed_ids()

    def test_primary_replace_failure_retains_original_and_receipt_recovery(self):
        self.seed()
        before=self.path.read_bytes();real_replace=state.os.replace
        def replace(source,target):
            if Path(target)==self.path:raise OSError(errno.EIO,'fixture disk failure')
            return real_replace(source,target)
        with patch.object(state.os,'replace',side_effect=replace),warnings.catch_warnings(record=True) as caught:
            result=state.record_published(['new'],'2026-11-02',slugs=['new-report'])
        self.assertEqual(result['status'],'receipt_only')
        self.assertTrue(caught)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(state.load_processed_ids(),{'existing','new'})
        self.path.unlink()
        self.assertEqual(state.load_processed_ids(),{'existing','new'})
        self.assertFalse(list(self.path.parent.glob('*.new')))

    def test_receipt_failure_does_not_block_when_primary_durable(self):
        self.seed();real=state._atomic_write
        def write(path,value):
            if Path(path).parent==state._receipt_dir(self.path):raise OSError(errno.ENOSPC,'fixture full receipt dir')
            return real(path,value)
        with patch.object(state,'_atomic_write',side_effect=write),warnings.catch_warnings(record=True):
            result=state.record_published(['new'],'2026-11-02')
        self.assertEqual(result['status'],'state_only')
        self.assertEqual(state.load_processed_ids(),{'existing','new'})

    def test_both_durability_paths_fail_explicitly_without_corrupting_old_history(self):
        self.seed();before=self.path.read_bytes()
        with patch.object(state,'_atomic_write',side_effect=OSError(errno.ENOSPC,'fixture full')):
            with self.assertRaises(state.ProcessedStateError):state.record_published(['new'],'2026-11-02')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(state.load_processed_ids(),{'existing'})

    def test_concurrent_writers_union_without_lost_updates(self):
        self.seed()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results=list(executor.map(lambda n:state.record_published([f'new-{n}'],'2026-11-02'),range(20)))
        self.assertEqual(state.load_processed_ids(),{'existing'}|{f'new-{n}' for n in range(20)})
        self.assertTrue(all(result['status']=='complete' for result in results))

    def test_failed_git_publication_never_creates_published_receipt(self):
        self.seed();staging=self.root/'staging';staging.mkdir();(staging/'report.html').write_text('validated')
        def git(args,**kwargs):
            if args[1]=='clone':Path(args[-1]).mkdir()
            return subprocess.CompletedProcess(args,0,stdout='fixture-remote')
        with patch.object(publisher.subprocess,'run',side_effect=git),patch.object(publisher,'commit_and_push',side_effect=RuntimeError('fixture push failed')),patch.object(publisher,'_update_processed_log') as record:
            with self.assertRaises(RuntimeError):publisher.publish(str(staging),'2026-11-02',{'report':{}},['unpublished'])
        record.assert_not_called()
        self.assertEqual(state.load_processed_ids(),{'existing'})

    def test_publish_returns_after_single_storage_failure_and_dry_run_never_records(self):
        self.seed();staging=self.root/'staging';staging.mkdir();(staging/'report.html').write_text('validated')
        def git(args,**kwargs):
            if args[1]=='clone':Path(args[-1]).mkdir()
            return subprocess.CompletedProcess(args,0,stdout='fixture-remote')
        real=state._atomic_write
        def write(path,value):
            if Path(path)==self.path:raise OSError(errno.EIO,'fixture primary failure')
            return real(path,value)
        with patch.object(publisher.subprocess,'run',side_effect=git),patch.object(publisher,'commit_and_push',return_value=True),patch.object(state,'_atomic_write',side_effect=write),warnings.catch_warnings(record=True):
            result=publisher.publish(str(staging),'2026-11-02',{'report':{}},['new'])
        self.assertTrue(result['changed'])
        self.assertEqual(pipeline.load_processed_ids(),{'existing','new'})
        with patch.object(publisher.subprocess,'run',side_effect=git),patch.object(publisher,'commit_and_push',return_value=True),patch.object(publisher,'_update_processed_log') as record:
            publisher.publish(str(staging),'2026-11-02',{'report':{}},['dry-run'],dry_run=True)
        record.assert_not_called()


if __name__=='__main__':unittest.main()
