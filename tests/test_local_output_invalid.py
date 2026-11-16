import json
"""Staged shared SDK compatibility: invalid local output cannot publish or pay."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aidaily.integrations import openrouter as llm
from aidaily.youtube_summaries import pipeline as youtube


class LocalOutputInvalidTests(unittest.TestCase):
    def test_invalid_local_output_blocks_generator_and_retry(self):
        sdk_path = Path(os.environ.get('AIDAILY_TEST_SDK',
                                      str(Path.home() / 'abot-inference/inference_client.py')))
        spec = importlib.util.spec_from_file_location('aidaily_output_validation_sdk', sdk_path)
        sdk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sdk)
        if not hasattr(sdk, 'LocalOutputInvalid'):
            self.skipTest('Installed SDK predates LocalOutputInvalid; supply AIDAILY_TEST_SDK for staged compatibility gate')
        client = Mock()
        client.chat.side_effect = sdk.LocalOutputInvalid('fixture-stable', 'fixture-job')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {'AIDAILY_LLM_STATE_DIR': str(Path(tmp) / 'receipts')}), \
             patch.object(llm, '_FLEET', sdk), patch.object(llm, '_new_client', return_value=client), \
             patch.object(llm, 'request_json') as paid, patch.object(youtube, 'publish') as publish, \
             patch.object(youtube, 'load_processed_ids', return_value=set()), \
             patch.object(youtube, 'load_config', return_value={'channels': []}), \
             patch.object(youtube, 'video_metadata', return_value={}), \
             patch.object(youtube, 'process_video', side_effect=lambda *a, **kw:
                          llm.complete('fixture system', 'fixture input', request_id='fixture-stable')):
            for _ in range(2):
                with patch('sys.argv', ['youtube-verification', '--url', 'https://youtu.be/abcdefghijk',
                                        '--staging-dir', tmp, '--publish']):
                    with self.assertRaises(SystemExit):
                        youtube.main()
                self.assertEqual(json.loads((Path(tmp) / youtube.QUEUE_NAME).read_text())["messages"], {})
            client.chat.assert_called_once()
            paid.assert_not_called()
            publish.assert_not_called()


if __name__ == '__main__': unittest.main()
