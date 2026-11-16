import os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.youtube_summaries import pipeline
from aidaily.integrations import openrouter

class FrozenYouTubeInput(unittest.TestCase):
    def test_pending_reexecution_across_new_staging_keeps_original_source_and_metadata(self):
        original={'video_id':'fixture-video','url':'https://example.invalid/source','title':'원래 제목','channel':'원래 채널'}
        changed={**original,'title':'수집 때 달라진 제목','channel':'변경 채널'}
        transcript='원래 수집한 긴 자막과 확정할 사실을 보존합니다. '*100
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'AIDAILY_YOUTUBE_CHECKPOINTS':root}),patch.object(pipeline.analyzer,'fetch_transcript',side_effect=[transcript,'변경된 자막 '*100]) as fetch,patch.object(pipeline.analyzer,'analyze',side_effect=openrouter.CompletionPending('stable')) as analyze,patch.object(pipeline,'render_report') as render:
            for metadata,staging in [(original,root+'/run-1'),(changed,root+'/run-2')]:
                Path(staging).mkdir()
                with self.assertRaises(openrouter.CompletionPending):pipeline.process_video(metadata,staging,'2026-10-04')
            fetch.assert_called_once();self.assertEqual(analyze.call_args_list[0],analyze.call_args_list[1]);render.assert_not_called()
            saved=json.loads(next(Path(root).glob('*.json')).read_text());self.assertEqual(saved['video']['title'],'원래 제목');self.assertEqual(saved['transcript'],transcript)

    def test_corrupted_frozen_input_does_not_generate_or_overwrite(self):
        v={'video_id':'fixture-video','url':'https://example.invalid/source','title':'제목','channel':'채널'}
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'AIDAILY_YOUTUBE_CHECKPOINTS':root}),patch.object(pipeline.analyzer,'fetch_transcript',return_value='충분한 원문 입력을 저장합니다. '*100):pipeline.frozen_input(v)
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'AIDAILY_YOUTUBE_CHECKPOINTS':root}),patch.object(pipeline.analyzer,'fetch_transcript',return_value='충분한 원문 입력을 저장합니다. '*100):
            pipeline.frozen_input(v);p=next(Path(root).glob('*.json'));d=json.loads(p.read_text());d['transcript']='변조된 원문';p.write_text(json.dumps(d));before=p.read_bytes()
            with patch.object(pipeline.analyzer,'analyze') as analyze,self.assertRaises(RuntimeError):pipeline.process_video(v,root,'2026-10-04')
            analyze.assert_not_called();self.assertEqual(p.read_bytes(),before)
