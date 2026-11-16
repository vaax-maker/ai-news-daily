import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from aidaily.notifications import captions, telegram, daily_digest


class AnnouncementRelayFormatTests(unittest.TestCase):
    def test_daily_and_republish_headers_share_relay_compatible_format(self):
        self.assertEqual(captions.daily_header('2026-10-13'), '오늘의 AI소식 · 10월13일(화)')
        self.assertEqual(captions.daily_header('2026-10-13', republished=True),
                         '오늘의 AI소식 · 10월13일(화)\n재발행 안내')
        for republished in (False, True):
            captions.validate_daily_header(captions.daily_header('2026-10-13', republished=republished))

    def test_blocked_iso_header_never_reaches_network(self):
        with patch.object(telegram, 'request_bytes') as network:
            with self.assertRaises(ValueError):
                telegram.send_photo('', '오늘의 AI소식 · 2026-10-13 재발행\n본문', 'token', 'chat')
            network.assert_not_called()

    def test_existing_bracket_announcements_are_unchanged(self):
        captions.validate_daily_header('[AI 비주얼 리포트] 2026-10-13\n본문')
        with self.assertRaises(ValueError):
            captions.daily_header('invalid-date')

    def test_bad_header_does_not_reserve_date_or_send(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telegram, 'send_photo') as send:
            with self.assertRaises(ValueError):
                daily_digest.send_once('2026-10-13', '오늘의 AI소식 · 2026-10-13', 'token', 'chat', directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
            send.assert_not_called()
