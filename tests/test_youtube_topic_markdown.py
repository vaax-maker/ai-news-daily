"""Verify topic-based and legacy reports through markdown and actual HTML rendering."""
import re
import tempfile
from pathlib import Path
import unittest
from aidaily.youtube_summaries import pipeline, renderer


class TopicMarkdownTests(unittest.TestCase):
    def report(self, count, *, new=True):
        report = {'card_summary': '영상 요약', 'overview': ['이전 형식의 개요'],
                  'sections': [{'title': f'영상 주제 {i}', 'bullets': [f'{i}번 세부 사실', f'{i}번 다른 사실']} for i in range(1, count + 1)],
                  'glossary': [{'term': '모델', 'definition': '영상에서 설명한 모델'}]}
        if new:
            report['report_schema'] = 'story_topics_v2'
        return report

    def test_topics_and_glossary_keep_source_order_without_display_numbers(self):
        for count in (1, 3, 5, 8):
            with self.subTest(count=count):
                markdown = pipeline.build_markdown(self.report(count), '영상 제목')
                heads = re.findall(r'^## (.+)$', markdown, re.M)
                self.assertEqual(heads, [f'영상 주제 {i}' for i in range(1, count + 1)] + ['용어 사전'])
                self.assertNotIn('핵심 개요', markdown)
                html = renderer.build_report(markdown, video_url='https://www.youtube.com/watch?v=abcdefghijk', show_section_numbers=False)
                cards = re.findall(r'<section class="card [^"]+" id="s(\d+)">\s*<h2>(.*?)</h2>', html, re.S)
                self.assertEqual(cards, [(str(i), f'영상 주제 {i}' if i <= count else '용어 사전') for i in range(1, count + 2)])
                self.assertNotIn('<span class="seq">', html)
                self.assertIn('영상에서 설명한 모델', html)
                for i in range(1, count + 1):
                    self.assertIn(f'{i}번 세부 사실', html)

    def test_future_pipeline_hides_numbers_and_marks_the_contract(self):
        report = self.report(3)
        report['category'] = 'tech'
        video = {'video_id': 'abcdefghijk', 'title': '원본 영상', 'channel': '채널',
                 'url': 'https://www.youtube.com/watch?v=abcdefghijk', 'category': 'tech'}
        with tempfile.TemporaryDirectory() as tmp:
            slug, _ = pipeline.write_analyzed_report(video, report, tmp, '2026-11-03', slug='2026-11-03-sample')
            page = (Path(tmp) / (slug + '.html')).read_text()
        self.assertNotIn('<span class="seq">', page)
        self.assertIn('<meta name="youtube-heading-numbering" content="none">', page)
        self.assertIn('id="s4"><h2>용어 사전</h2>', page)
        self.assertIn('youtube.com/embed/abcdefghijk', page)

    def test_legacy_without_schema_keeps_overview_and_glossary(self):
        markdown = pipeline.build_markdown(self.report(2, new=False), '예전 영상')
        heads = re.findall(r'^## (.+)$', markdown, re.M)
        self.assertEqual(heads, ['핵심 개요', '영상 주제 1', '영상 주제 2', '용어 사전'])
        html = renderer.build_report(markdown)
        self.assertIn('이전 형식의 개요', html)
        self.assertIn('<section class="card s', html)


if __name__ == '__main__':
    unittest.main()
