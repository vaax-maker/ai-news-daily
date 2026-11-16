"""Offline title→ASR→future report spelling context regressions."""
import html
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from aidaily.integrations import youtube, youtube_transcript as transcript
from aidaily.youtube_summaries import pipeline


class TitleContextTests(unittest.TestCase):
    def test_context_uses_original_title_and_only_active_canonical_terms(self):
        dictionary = {'terms': [
            {'canonical': 'Higgsfield', 'enabled': True},
            {'canonical': 'DisabledName', 'enabled': False},
            {'canonical': 'OtherDomain', 'context': ['not-present']}]}
        with patch('aidaily.integrations.terminology.load_glossary', return_value=dictionary):
            prompt = transcript._initial_prompt('힉스필드 신기능 원래 제목', '원래 채널')
        self.assertIn('힉스필드 신기능 원래 제목', prompt)
        self.assertIn('Higgsfield', prompt)
        self.assertNotIn('DisabledName', prompt)
        self.assertNotIn('OtherDomain', prompt)
        self.assertLessEqual(len(prompt), 400)

    def test_fetch_default_keeps_raw_and_old_call_signature(self):
        raw = '픽스필드 원문'
        with patch.object(youtube, 'transcribe', return_value={'transcript': raw}) as call:
            self.assertEqual(youtube.fetch_transcript('url'), raw)
            call.assert_called_once_with('url', lang='ko')
        with patch.object(youtube, 'transcribe', return_value={'transcript': raw}) as call:
            self.assertEqual(youtube.fetch_transcript('url', title='힉스필드', channel='채널'), raw)
            call.assert_called_once_with('url', lang='ko', title='힉스필드', channel='채널')

    def test_transcribe_forwards_prompt_only_for_context_calls(self):
        with patch.dict(os.environ, {'YOUTUBE_MIN_TRANSCRIPT_CHARS': '1'}), patch.object(transcript, '_yt_subs', return_value=None), patch.object(transcript, '_yt_asr', return_value=([{'text': '원문'}], 'asr')) as asr:
            transcript.transcribe('abcdefghijk')
            self.assertEqual(asr.call_args.kwargs, {})
            transcript.transcribe('abcdefghijk', title='힉스필드 제목', channel='채널')
            self.assertIn('힉스필드 제목', asr.call_args.kwargs['initial_prompt'])

    def test_whisper_cli_receives_optional_initial_prompt(self):
        with patch.object(transcript.subprocess, 'run', return_value=Mock(returncode=0)) as run, patch.object(transcript.glob, 'glob', return_value=[]):
            transcript._whisper('audio.wav', 'ko', '/tmp', initial_prompt='힉스필드, Higgsfield')
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index('--initial-prompt')+1], '힉스필드, Higgsfield')
            transcript._whisper('audio.wav', 'ko', '/tmp')
            self.assertNotIn('--initial-prompt', run.call_args.args[0])

    def test_prompt_survives_download_and_audio_preprocessing_chain(self):
        with patch.object(transcript.subprocess, 'run', return_value=Mock(returncode=0)), patch.object(transcript.glob, 'glob', return_value=['/tmp/audio.m4a']), patch.object(transcript.os.path, 'getsize', return_value=1), patch.object(transcript, '_asr', return_value=None) as asr:
            transcript._yt_asr('url', 'ko', '/tmp', initial_prompt='힉스필드')
            asr.assert_called_once_with('/tmp/audio.m4a', 'ko', '/tmp', initial_prompt='힉스필드')
        with patch.object(transcript, '_to_16k_wav', return_value=None), patch.object(transcript, '_whisper', return_value=None) as whisper:
            transcript._asr('audio.m4a', 'ko', '/tmp', initial_prompt='힉스필드')
            whisper.assert_called_once_with('audio.m4a', 'ko', '/tmp', initial_prompt='힉스필드')

    def test_checkpoint_reuse_preserves_bytes_and_future_report_exact_metadata(self):
        video = {'video_id': 'title-test', 'url': 'https://example.invalid/source',
                 'title': '힉스필드 "원제목" <새 기능>', 'channel': '원래 & 채널', 'category': 'tech', 'upload_date': '2026-10-21'}
        raw = '픽스필드라는 전사 원문을 그대로 보존합니다. '*100
        analysis = {'category': 'tech', 'headline': '생성한 다른 헤드라인'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AIDAILY_YOUTUBE_CHECKPOINTS': tmp}), patch.object(pipeline.analyzer, 'fetch_transcript', return_value=raw) as fetch:
            pipeline.frozen_input(video)
            checkpoint = next(Path(tmp).glob('*.json'))
            before = checkpoint.read_bytes()
            fetch.assert_called_once_with(video['url'], title=video['title'], channel=video['channel'])
            with patch.object(pipeline.analyzer, 'analyze', return_value=analysis), patch.object(pipeline, 'build_slug', return_value='fixture') as slug_builder, patch.object(pipeline, 'build_markdown', return_value='md'), patch.object(pipeline, '_bullet_msg', return_value='message'), patch.object(pipeline, 'render_report', side_effect=lambda md, out, *args, **kwargs: Path(out).write_text('<html><head></head><body>rendered</body></html>')):
                pipeline.process_video({**video, 'title': '나중 제목'}, tmp, '2026-10-22')
                self.assertEqual(slug_builder.call_args.args[2], '2026-10-22')
            report = (Path(tmp)/'fixture.html').read_text()
            self.assertIn('name="youtube-source-title" content="'+html.escape(video['title'], quote=True)+'"', report)
            self.assertIn('name="youtube-source-channel" content="원래 &amp; 채널"', report)
            self.assertNotIn('content="나중 제목"', report)
            self.assertEqual(before, checkpoint.read_bytes())
            self.assertEqual(json.loads(before)['transcript'], raw)


if __name__ == '__main__':
    unittest.main()
