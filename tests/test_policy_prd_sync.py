"""Isolated policy PRD synchronization checks; no network or publication."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location('policy_prd_sync_under_test', Path(__file__).resolve().parents[1] / 'deploy/sync_policy_prd.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class PolicyPrdSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / 'aidaily'
        self.root.mkdir()
        self.state = self.root / 'data/policy_prd'
        self.state.mkdir(parents=True)
        self.output = self.root / 'operations/policy-prd/output'
        self.policy = self.root / 'operations/policy-prd/POLICY.md'
        self.policy.parent.mkdir(parents=True)
        self.policy.write_text('# Policy\n')
        for name, value in dict(HOME=self.home, ROOT=self.root, STATE=self.state, OUTPUT=self.output, POLICY=self.policy).items():
            p = patch.object(sync, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.launch = patch.object(sync.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr=''))
        self.launch.start()
        self.addCleanup(self.launch.stop)

    def write(self, path, value):
        p = self.home / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value) if isinstance(value, dict) else value)
        return p

    def run_main(self, publish=False):
        with patch('sys.argv', ['sync_policy_prd.py'] + (['--publish'] if publish else [])):
            sync.main()

    def test_change_detection_and_no_change_does_not_rebuild(self):
        source = self.write('aidaily/aidaily/example.py', 'x=1')
        self.write('aidaily/.env', 'SECRET_MUST_NOT_BE_READ')
        self.write('aidaily/data/raw-chat.json', {'secret': 'private'})
        self.run_main()
        first = json.loads((self.state/'state.json').read_text())
        self.assertNotIn('aidaily/.env', first['manifest'])
        with patch.object(sync, 'build', side_effect=AssertionError('unchanged build')):
            self.run_main()
        source.write_text('x=2')
        self.run_main()
        second = json.loads((self.state/'state.json').read_text())
        self.assertNotEqual(first['built_digest'], second['built_digest'])

    def test_confidentiality_allowlist_excludes_unknown_secret_fields(self):
        self.write('aidaily/data/content-settings.json', {'version': 1, 'api_key': 'CONFIDENTIAL_KEY'})
        self.write('Sites/ai-infographic/daybreak-config.json', {'hours': 48, 'token': 'CONFIDENTIAL_TOKEN', 'channels': [{'name':'public', 'channel_id':'UCexample', 'private_note':'CONFIDENTIAL_NOTE'}]})
        self.write('aidaily/operations/refresh-schedule-application.json', {'status':'applied', 'password':'CONFIDENTIAL_PASSWORD'})
        sync.build(sync.manifest(), {})
        public_text = '\n'.join(p.read_text() for p in self.output.iterdir())
        for secret in ['CONFIDENTIAL_KEY', 'CONFIDENTIAL_TOKEN', 'CONFIDENTIAL_NOTE', 'CONFIDENTIAL_PASSWORD']:
            self.assertNotIn(secret, public_text)

    def test_allowlist_retains_valid_policy_and_channel_fields(self):
        settings={'collection':{'ai_news':{'enabled':True,'since_days':3}}, 'sources':[{'id':'ai-times','name':'AI타임스','limit':3,'enabled':True}], 'infographics':{'ai_news':{'enabled':False}}, 'market_summary':{'enabled':False}}
        youtube={'hours':48,'min_duration':240,'channels':[{'handle':'@example','channel_id':'UCexample','category':'tech','field':'AI','title_include':['AI']}],'infographic_enabled':True}
        self.write('aidaily/data/content-settings.json',settings)
        self.write('Sites/ai-infographic/daybreak-config.json',youtube)
        sync.build(sync.manifest(), {})
        snapshot=json.loads((self.output/'policy-snapshot.json').read_text())
        self.assertEqual(snapshot['settings']['collection']['ai_news'],settings['collection']['ai_news'])
        self.assertEqual(snapshot['settings']['sources'][0]['limit'],3)
        self.assertEqual(snapshot['youtube'],youtube)

    def test_semantic_warning_persists_until_explicit_review(self):
        self.write('aidaily/aidaily/example.py', 'x=1')
        self.run_main()
        self.assertTrue(json.loads((self.output/'policy-snapshot.json').read_text())['semantic_review_required'])
        self.write('aidaily/README.md', '# changed documentation unrelated to code review')
        self.run_main()
        self.assertTrue(json.loads((self.output/'policy-snapshot.json').read_text())['semantic_review_required'])

    def test_explicit_review_acknowledgement_clears_warning(self):
        self.write('aidaily/aidaily/example.py', 'x=1')
        self.run_main()
        with patch('sys.argv',['sync_policy_prd.py','--acknowledge-policy-review']):
            sync.main()
        self.assertFalse(json.loads((self.output/'policy-snapshot.json').read_text())['semantic_review_required'])
        self.assertFalse(json.loads((self.state/'state.json').read_text())['semantic_review_required'])

    def test_uncertain_transaction_resumes_before_source_rebuild(self):
        state = {'built_digest':'old', 'pending_transaction':'mini1-'+'a'*24, 'submission_uncertain':True}
        (self.state/'state.json').write_text(json.dumps(state))
        result = SimpleNamespace(returncode=0, stdout=json.dumps({'ok':True,'url':'https://example.invalid/p/aidaily-policy/'}), stderr='')
        with patch.object(sync, 'manifest', side_effect=AssertionError('must freeze output while resuming')), patch.object(sync.subprocess, 'run', return_value=result) as run:
            self.run_main(publish=True)
        self.assertEqual(run.call_args.args[0][-2:], ['--resume',state['pending_transaction']])
        saved = json.loads((self.state/'state.json').read_text())
        self.assertEqual(saved['published_digest'], 'old')
        self.assertFalse(saved['submission_uncertain'])
        self.assertNotIn('pending_transaction', saved)

    def test_readonly_preflight_failure_allows_retry(self):
        state={'built_digest':'a'}
        result=SimpleNamespace(returncode=1, stdout='', stderr='central_storage_preflight_unavailable')
        with patch.object(sync.subprocess,'run',return_value=result):
            with self.assertRaises(RuntimeError):sync.publish(state)
        self.assertFalse(json.loads((self.state/'state.json').read_text())['submission_uncertain'])

    def test_existing_transaction_preflight_error_keeps_output_frozen(self):
        state={'built_digest':'old', 'pending_transaction':'mini1-'+'c'*24, 'submission_uncertain':True}
        result=SimpleNamespace(returncode=1, stdout='', stderr='central_storage_preflight_unavailable')
        with patch.object(sync.subprocess,'run',return_value=result):
            with self.assertRaises(RuntimeError):sync.publish(state)
        saved=json.loads((self.state/'state.json').read_text())
        self.assertTrue(saved['submission_uncertain'], 'An old transaction must remain frozen; do not rebuild and attribute its success to a newer digest')

    def test_timeout_preserves_uncertainty_before_external_call(self):
        state={'built_digest':'a'}
        with patch.object(sync.subprocess,'run',side_effect=subprocess.TimeoutExpired('register',600)):
            with self.assertRaises(subprocess.TimeoutExpired):sync.publish(state)
        self.assertTrue(json.loads((self.state/'state.json').read_text())['submission_uncertain'])

    def test_unknown_submission_failure_blocks_duplicate(self):
        state={'built_digest':'a'}
        result=SimpleNamespace(returncode=1, stdout='', stderr='connection lost after submit')
        with patch.object(sync.subprocess,'run',return_value=result) as run:
            with self.assertRaises(RuntimeError):sync.publish(state)
            saved=json.loads((self.state/'state.json').read_text())
            self.assertTrue(saved['submission_uncertain'])
            with self.assertRaisesRegex(RuntimeError,'Unknown publication outcome'):sync.publish(saved)
        self.assertEqual(run.call_count,1)

    def test_failed_known_transaction_preserved_for_resume(self):
        txn='drive-'+'b'*24
        state={'built_digest':'a'}
        result=SimpleNamespace(returncode=1, stdout=json.dumps({'ok':False,'transaction':txn}), stderr='incomplete')
        with patch.object(sync.subprocess,'run',return_value=result):
            with self.assertRaises(RuntimeError):sync.publish(state)
        saved=json.loads((self.state/'state.json').read_text())
        self.assertTrue(saved['submission_uncertain'])
        self.assertEqual(saved['pending_transaction'],txn)


if __name__ == '__main__':
    unittest.main()
