"""Gate-withheld runs are not expected publicly; shape rejections are not retried daily."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aidaily import config
from aidaily.publishing import youtube_verification as verification
from aidaily.youtube_summaries import analyzer, pipeline

DATE = '2026-11-14'


class WithheldRunVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        p = patch.object(config, 'DATA_ROOT', Path(self.temp.name)); p.start(); self.addCleanup(p.stop)
        self.stage = Path(self.temp.name) / 'youtube_summaries/staging' / DATE
        self.stage.mkdir(parents=True)
        self.receipt = {'date': DATE, 'target_count': 10, 'done_ids': ['abcdefghijk'],
                        'queue': {DATE + '-x': {}}, 'report_hashes': {DATE + '-x': '0' * 64}}

    def write(self):
        (self.stage / 'run-status.json').write_text(json.dumps(self.receipt))

    def test_failed_gate_expects_nothing_and_makes_no_requests(self):
        self.receipt['quality_gate'] = {'status': 'failed', 'succeeded': 2, 'required': 3}
        self.write()
        def opener(*args, **kwargs):
            raise AssertionError('no HTTPS request expected')
        result = verification.verify_youtube_publication(DATE, opener=opener)
        self.assertEqual(result['youtube_reports'], 0)
        self.assertEqual(result['youtube_status'], 'withheld_quality_gate')

    def test_passed_or_missing_gate_still_requires_exact_reports(self):
        for gate in ({'status': 'passed'}, None):
            with self.subTest(gate=gate):
                self.receipt.pop('quality_gate', None)
                if gate: self.receipt['quality_gate'] = gate
                self.write()
                with self.assertRaises(RuntimeError):
                    verification.verify_youtube_publication(DATE, opener=lambda *a, **k: None)

    def test_record_quality_gate_preserves_receipt(self):
        self.write()
        pipeline.record_quality_gate(str(self.stage), DATE, 'failed', succeeded=2, required=3)
        saved = json.loads((self.stage / 'run-status.json').read_text())
        self.assertEqual(saved['quality_gate'], {'status': 'failed', 'succeeded': 2, 'required': 3})
        self.assertEqual(saved['done_ids'], self.receipt['done_ids'])
        with self.assertRaises(RuntimeError):
            pipeline.record_quality_gate(str(self.stage), '2026-11-13', 'failed')


class ShapeRejection(unittest.TestCase):
    def test_validator_raises_quality_error_that_is_still_runtime_error(self):
        with self.assertRaises(analyzer.ReportQualityError) as caught:
            analyzer._validate_report({'sections': []}, require_explanations=True)
        self.assertIsInstance(caught.exception, RuntimeError)

    def run_with_previous(self, failure):
        with tempfile.TemporaryDirectory() as root:
            previous = Path(root, '2026-11-13'); previous.mkdir()
            Path(previous, 'run-status.json').write_text(json.dumps({'done_ids': [], 'failures': [failure]}))
            current = str(Path(root, DATE))
            video = failure['video']
            with patch.object(pipeline, 'DEFAULT_STAGING', current), \
                 patch.object(pipeline, 'load_processed_ids', return_value=set()), \
                 patch.object(pipeline, 'load_config', return_value={}), \
                 patch.object(pipeline, 'collect_targets', return_value=[dict(video)]), \
                 patch.object(pipeline, 'process_video', return_value=('done', {})) as process:
                return pipeline.run([], current, 10), process

    def test_current_prompt_rejection_is_not_reselected(self):
        video = {'video_id': 'rejected123', 'title': 't', 'url': 'https://example.invalid'}
        result, process = self.run_with_previous({'video_id': 'rejected123', 'video': video,
            'state': 'quality_rejected', 'prompt_sha': analyzer.PROMPT_SHA})
        process.assert_not_called(); self.assertEqual(result['target_count'], 0)

    def test_rejection_under_old_prompt_is_retried(self):
        video = {'video_id': 'rejected123', 'title': 't', 'url': 'https://example.invalid'}
        result, process = self.run_with_previous({'video_id': 'rejected123', 'video': video,
            'state': 'quality_rejected', 'prompt_sha': 'old'})
        self.assertEqual(result['done_ids'], ['rejected123'])

    def test_new_shape_failure_is_recorded_as_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            current = str(Path(root, DATE))
            video = {'video_id': 'newfail1234', 'title': 't', 'url': 'https://example.invalid'}
            with patch.object(pipeline, 'DEFAULT_STAGING', current), \
                 patch.object(pipeline, 'load_processed_ids', return_value=set()), \
                 patch.object(pipeline, 'load_config', return_value={}), \
                 patch.object(pipeline, 'collect_targets', return_value=[video]), \
                 patch.object(pipeline, 'process_video', side_effect=analyzer.ReportQualityError('섹션 1')):
                result = pipeline.run([], current, 10)
            failure = result['failures'][0]
            self.assertEqual(failure['state'], 'quality_rejected')
            self.assertEqual(failure['prompt_sha'], analyzer.PROMPT_SHA)

    def test_short_bullet_is_merged_instead_of_rejecting(self):
        long_a = '가' * 60 + '라고 설명한다.'
        short = '비용은 2.2%라고 설명한다.'
        report = {'sections': [{'title': '비용 구조', 'bullets': [long_a, short]}],
                  'glossary': [{'term': f't{i}', 'definition': 'd'} for i in range(3)]}
        out = analyzer._validate_report(report, require_explanations=True)
        self.assertEqual(out['sections'][0]['bullets'], [long_a + ' ' + short])

    def test_unmergeable_short_bullet_still_rejected(self):
        report = {'sections': [{'title': '비용 구조', 'bullets': ['가' * 175 + '이다.', '짧다.']}],
                  'glossary': [{'term': f't{i}', 'definition': 'd'} for i in range(3)]}
        with self.assertRaises(analyzer.ReportQualityError):
            analyzer._validate_report(report, require_explanations=True)


class RequiredChannels(unittest.TestCase):
    def test_required_videos_are_attempted_beyond_the_daily_cap(self):
        ordinary = [{'video_id': f'ordinary{i:03d}', 'title': f'o{i}', 'url': 'u'} for i in range(5)]
        required = [{'video_id': f'required{i:03d}', 'title': f'r{i}', 'url': 'u', '_required': True} for i in range(3)]
        def process(v, root, date):
            Path(root, v['video_id'] + '.html').write_text('x'); return v['video_id'], {'text': 't'}
        with tempfile.TemporaryDirectory() as root:
            current = str(Path(root, DATE))
            with patch.object(pipeline, 'DEFAULT_STAGING', current), \
                 patch.object(pipeline, 'load_processed_ids', return_value=set()), \
                 patch.object(pipeline, 'load_config', return_value={}), \
                 patch.object(pipeline, 'collect_targets', return_value=required + ordinary), \
                 patch.object(pipeline, 'process_video', side_effect=process):
                result = pipeline.run([], current, 2)
        self.assertEqual(set(result['done_ids']), {v['video_id'] for v in required} | {'ordinary000', 'ordinary001'})
        self.assertEqual(result['target_count'], 5)

    def test_collect_targets_keeps_all_required_channel_videos(self):
        cfg = {'channels': [{'channel_id': 'A', 'handle': 'a'}, {'channel_id': 'R', 'handle': 'r', 'required': True}]}
        def listing(cid, *args, **kwargs):
            if kwargs.get('xr_only'): return []
            return [{'video_id': f'{cid}{i:010d}', 'title': 't', 'published_at': '', 'url': 'u'} for i in range(4)]
        with patch.object(pipeline, 'list_channel_videos', side_effect=listing):
            targets = pipeline.collect_targets(cfg, set(), 2)
        self.assertEqual(sum(1 for v in targets if v.get('_required')), 4)
        self.assertEqual(sum(1 for v in targets if not v.get('_required')), 2)


if __name__ == '__main__':
    unittest.main()
