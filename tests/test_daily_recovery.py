"""Daily recovery orchestration regressions with no network or external messages."""
import io
import datetime
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aidaily import config
from aidaily.publishing import daily, pipeline
from aidaily.notifications import daily_digest


class DailyRecoveryTests(unittest.TestCase):
    date = '2026-10-20'

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(daily, 'ADMIN_CONFIG_PATH', self.root/'admin-notifications.json', create=True))
        # Even a future credential fallback cannot make this test contact Telegram.
        self.stack.enter_context(patch('aidaily.notifications.telegram.send_admin_text',
                                      side_effect=AssertionError('Unexpected real admin send')))
        self.stack.enter_context(patch.multiple(config, PROJECT_ROOT=self.root,
            DOCS_ROOT=self.root/'docs', DATA_ROOT=self.root/'data',
            PUBLISHING_REPOSITORY=self.root/'site'))
        self.stack.enter_context(patch.dict('os.environ', {
            'AIDAILY_ADMIN_TELEGRAM_TOKEN': '', 'AIDAILY_ADMIN_TELEGRAM_CHAT_ID': ''}))
        self.write('docs/archive/index.json', [{'date': self.date, 'stories': [{'body_bullets':['News']}]}])
        self.write('docs/daily.html', 'today news')
        self.write(f'docs/v2/uservoice/{self.date}.html', f'today usage {self.date}')
        self.write(f'data/customer_stories/{self.date}.json', {'date': self.date, 'gen': {'items':[{'title':'usage'}]}})
        self.write('docs/search-index.json', [{'date':self.date, 'kind':'ai_news', 'title':'New launch'}])
        self.write('site/index.html', 'site')
        self.calls = []

    def write(self, path, value):
        target = self.root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value) if isinstance(value, (dict,list)) else value)

    def command(self, arguments, **kwargs):
        module = arguments[2]
        self.calls.append(module)
        if module == 'aidaily.notifications.daily_digest':
            self.write(f'data/notifications/daily_digest/{self.date}.json', {'status':'sent'})
        return SimpleNamespace(returncode=0)

    def test_resume_reuses_generation_and_publication(self):
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status':200}) as verify:
            daily.run_day(self.date)
            daily.run_day(self.date)
        self.assertEqual(verify.call_count, 2)
        for module in ['aidaily.customer_stories.pipeline', 'aidaily.ai_news.pipeline', 'aidaily.publishing.pipeline']:
            self.assertEqual(self.calls.count(module), 1)

    def test_prepare_defers_release_and_release_reuses_generation(self):
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status':200}) as verify:
            daily.run_day(self.date, prepare_only=True)
            self.assertEqual(self.calls, ['aidaily.customer_stories.pipeline', 'aidaily.ai_news.pipeline'])
            verify.assert_not_called()
            state = json.loads((self.root/f'data/publishing/daily_runs/{self.date}.json').read_text())
            self.assertEqual(state['status'], 'prepared')
            daily.run_day(self.date)
        self.assertEqual(self.calls, ['aidaily.customer_stories.pipeline', 'aidaily.ai_news.pipeline',
                                     'aidaily.publishing.pipeline', 'aidaily.notifications.daily_digest'])
        self.assertEqual(verify.call_count, 1)

    def test_scheduled_release_uses_waiting_lock(self):
        with patch.object(daily.fcntl, 'flock') as flock, patch.object(
                daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status':200}):
            daily.run_day(self.date, wait_for_lock=True)
        self.assertEqual(flock.call_args.args[1], daily.fcntl.LOCK_EX)
        self.assertIn('aidaily.publishing.pipeline', self.calls)

    def test_failed_publication_stops_verification_and_notification(self):
        def command(arguments, **kwargs):
            result = self.command(arguments, **kwargs)
            if arguments[2] == 'aidaily.publishing.pipeline':
                result.returncode = 1
            return result
        with patch.object(daily.subprocess, 'run', side_effect=command), patch.object(daily, 'verify_publication') as verify:
            with self.assertRaises(RuntimeError):
                daily.run_day(self.date)
        verify.assert_not_called()
        self.assertNotIn('aidaily.notifications.daily_digest', self.calls)
        state=json.loads((self.root/f'data/publishing/daily_runs/{self.date}.json').read_text())
        self.assertEqual(state['current_stage'], 'publish')
        self.assertEqual(state['status'], 'failed')

    def test_adopts_todays_known_outputs(self):
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status':200}):
            daily.run_day(self.date, adopt_generated=True, no_notify=True)
        self.assertEqual(self.calls, ['aidaily.publishing.pipeline'])

    def test_no_notify_records_unnotified_and_recovery_sends_once(self):
        state_path = self.root/f'data/publishing/daily_runs/{self.date}.json'
        self.write(str(state_path.relative_to(self.root)), {'date': self.date,
            'status': 'failed', 'current_stage': 'publish', 'error_type': 'RuntimeError', 'stages': {}})
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status': 200}):
            daily.run_day(self.date, adopt_generated=True, no_notify=True)
            state = json.loads(state_path.read_text())
            self.assertEqual(state['status'], 'published_unnotified')
            self.assertEqual(state['publication_status'], 'verified')
            self.assertEqual(state['notification_status'], 'not_sent')
            self.assertEqual(state['stages']['notify']['status'], 'deferred')
            self.assertNotIn('error_type', state)
            self.assertEqual(state['recovery_history'][0]['error_type'], 'RuntimeError')
            self.calls.clear()
            daily.run_day(self.date, notify_only=True)
            daily.run_day(self.date, notify_only=True)
        self.assertEqual(self.calls, ['aidaily.notifications.daily_digest'])
        state = json.loads(state_path.read_text())
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['notification_status'], 'sent')

    def test_notify_only_never_resends_uncertain_or_unreadable_receipt(self):
        for receipt in ({'status': 'uncertain'}, {'status': 'sending'}, 'corrupt json'):
            self.write(f'data/notifications/daily_digest/{self.date}.json', receipt)
            self.calls.clear()
            with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                    daily, 'verify_publication', return_value={'http_status': 200}):
                with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                    daily.run_day(self.date, notify_only=True)
            self.assertEqual(self.calls, [])

    def test_notify_only_verifies_before_sending(self):
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', side_effect=RuntimeError('stale page')):
            with self.assertRaisesRegex(RuntimeError, 'stale page'):
                daily.run_day(self.date, notify_only=True)
        self.assertEqual(self.calls, [])

    def test_no_notify_with_sent_receipt_remains_complete(self):
        self.write(f'data/notifications/daily_digest/{self.date}.json', {'status': 'sent'})
        with patch.object(daily.subprocess, 'run', side_effect=self.command), patch.object(
                daily, 'verify_publication', return_value={'http_status': 200}):
            daily.run_day(self.date, adopt_generated=True, no_notify=True)
        self.assertEqual(json.loads((self.root/f'data/publishing/daily_runs/{self.date}.json').read_text())['status'], 'complete')

    def test_stale_https_blocks_notification(self):
        class Response(io.BytesIO):
            status=200
        def opener(*args, **kwargs):
            return Response(b'<h1>2026.10.19</h1>New launch')
        with self.assertRaisesRegex(RuntimeError, 'not yet confirmed'):
            daily.verify_publication(self.date, attempts=1, opener=opener)
        with patch.object(daily.subprocess,'run',side_effect=self.command), patch.object(
                daily,'verify_publication',side_effect=RuntimeError('stale page')):
            with self.assertRaises(RuntimeError):
                daily.run_day(self.date, adopt_generated=True)
        self.assertNotIn('aidaily.notifications.daily_digest', self.calls)

    def test_current_news_with_missing_youtube_never_passes_verification(self):
        class Response(io.BytesIO):
            status = 200
        def opener(*args, **kwargs):
            return Response((self.date.replace('-', '.') + ' New launch').encode())
        with patch('aidaily.publishing.youtube_verification.verify_youtube_publication',
                   side_effect=RuntimeError('required infographic missing')) as verify:
            with self.assertRaisesRegex(RuntimeError, 'required infographic missing'):
                daily.verify_publication(self.date, attempts=1, opener=opener)
            verify.assert_called_once_with(self.date, opener=opener)

    def test_customer_stale_or_missing_artifact_is_regenerated(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                state=self.root/f'data/publishing/daily_runs/{self.date}.json'
                state.unlink(missing_ok=True)
                self.calls.clear()
                page=self.root/f'docs/v2/uservoice/{self.date}.html'
                if missing:
                    page.unlink(missing_ok=True)
                else:
                    page.write_text('2026-10-19 stale usage')
                self.assertFalse(daily.customer_generated(self.date))
                with patch.object(daily.subprocess,'run',side_effect=self.command), patch.object(
                        daily,'verify_publication',return_value={'http_status':200}):
                    daily.run_day(self.date,adopt_generated=True,no_notify=True)
                self.assertIn('aidaily.customer_stories.pipeline',self.calls)
                self.assertNotIn('aidaily.ai_news.pipeline',self.calls)

    def test_uncertain_notification_is_not_resent(self):
        receipts=self.root/'receipts'
        with patch.object(daily_digest.captions,'validate_daily_header'), patch.object(
                daily_digest.telegram,'send_photo',side_effect=TimeoutError('ambiguous')) as send:
            with self.assertRaises(TimeoutError):
                daily_digest.send_once(self.date,'caption','token','chat',receipts)
            self.assertEqual(daily_digest.send_once(self.date,'caption','token','chat',receipts)['status'],
                             'skipped_existing_receipt')
            self.assertEqual(send.call_count,1)
        self.assertEqual(json.loads((receipts/f'{self.date}.json').read_text())['status'],'uncertain')

    def test_admin_uncertain_alert_is_reserved_and_not_resent(self):
        state={'date':self.date,'stages':{}}
        target=self.root/'incident/state.json'
        reservations=[]
        def uncertain_send(*args):
            saved=json.loads(target.read_text())
            reservations.append(next(iter(saved['alerts'].values()))['status'])
            raise TimeoutError('ambiguous delivery')
        with patch.dict('os.environ',{'AIDAILY_ADMIN_TELEGRAM_TOKEN':'fake-token',
                'AIDAILY_ADMIN_TELEGRAM_CHAT_ID':'fake-chat'}), patch(
                'aidaily.notifications.telegram.send_admin_text',side_effect=uncertain_send) as send:
            daily.alert_failure(state,target,'publish',RuntimeError('first'))
            # Resume from disk, as a later invocation would.
            state=json.loads(target.read_text())
            daily.alert_failure(state,target,'publish',RuntimeError('same stage and type'))
        self.assertEqual(send.call_count,1)
        self.assertEqual(reservations,['sending'])
        self.assertEqual(next(iter(state['alerts'].values()))['status'],'uncertain')

    def test_public_outputs_excludes_internal_documents(self):
        for path in ['docs/TODO.md','docs/fleet-inference-acceptance.json', 'docs/private.json', 'docs/credentials.txt']:
            self.write(path,'internal')
        outputs=pipeline.public_outputs(self.date)
        self.assertIn('docs/daily.html',outputs)
        self.assertIn(f'docs/v2/uservoice/{self.date}.html',outputs)
        self.assertTrue(all('TODO' not in path and 'acceptance' not in path and 'private' not in path and 'credentials' not in path for path in outputs))

    def test_current_approval_hold_blocks_before_network(self):
        today=datetime.date.today().isoformat()
        self.write('data/publishing/publication-hold.json',{'date':today,'status':'approval_required'})
        with patch('sys.argv',['publishing']), patch.object(pipeline,'rebuild_search_index') as rebuild, \
                patch.object(pipeline,'publish_aidaily') as publish, patch.object(pipeline.subprocess,'run') as network:
            with self.assertRaisesRegex(RuntimeError,'approval hold'):
                pipeline.main()
        rebuild.assert_not_called()
        publish.assert_not_called()
        network.assert_not_called()
        # Historical holds and explicitly released holds leave current publication enabled.
        for hold in ({'date':'2000-01-01','status':'approval_required'},
                     {'date':today,'status':'released'}):
            with self.subTest(hold=hold):
                self.write('data/publishing/publication-hold.json',hold)
                pipeline.ensure_release_allowed()


if __name__ == '__main__':
    unittest.main()
