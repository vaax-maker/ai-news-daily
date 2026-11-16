import tempfile
import unittest
from pathlib import Path
from aidaily.publishing.search_index import load_individual_reports


class ReportEvidenceIndex(unittest.TestCase):
    def test_current_report_preserves_literal_overview_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, '2026-10-12-test.html').write_text(
                '<title>테스트</title><body class="cat-tech">'
                'YOUTUBE SUMMARIES · 2026-10-12 · 채널'
                '<p class="lead">개요</p><section id="s1">'
                '<ul><li>연구원 <strong>3명 중 2명</strong>이 참여했다.</li>'
                '<li>비용은 20% 하락했다.</li></ul></section></body>')
            rows = load_individual_reports(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['summary_bullets'],
                             ['연구원 3명 중 2명이 참여했다.', '비용은 20% 하락했다.'])
            self.assertNotIn('<strong>', rows[0]['summary'])

