import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from aidaily.publishing import horizon_verification as verify


class Response:
    status = 200
    def __init__(self, text): self.text = text
    def read(self): return self.text.encode('utf-8')
    def __enter__(self): return self
    def __exit__(self, *args): pass


class HorizonPublicationTests(unittest.TestCase):
    def setUp(self):
        self.date = '2026-11-03'
        self.edition = {'date': self.date, 'status': 'complete', 'items': [
            {'id': 'one', 'title': '첫 자료', 'url': 'https://example.org/one',
             'source_name': '원문 매체', 'bullets': ['검증할 본문 내용'], 'reason': '선정 근거'}],
            'sources': [{'name': '수집 출처', 'url': 'https://example.org/feed'}]}
        self.page = ('<section id="horizon-briefing" data-horizon-date="2026-11-03" '
                     'data-horizon-status="complete"><article data-horizon-item="one">'
                     '<a href="https://example.org/one">첫 자료</a> 원문 매체 검증할 본문 내용 선정 근거'
                     '</article><a href="https://example.org/feed">수집 출처</a></section>')

    def call(self, page):
        with patch.object(verify, 'load_editions', return_value={self.date: self.edition}):
            return verify.verify_horizon_publication(self.date, opener=lambda *a, **kw: Response(page))

    def test_exact_edition_passes(self):
        result = self.call(self.page)
        self.assertTrue(result['exact_edition'])
        self.assertEqual(result['items'], 1)

    def test_stale_date_missing_body_and_missing_link_fail(self):
        for page in (self.page.replace('2026-11-03', '2026-11-02'),
                     self.page.replace('검증할 본문 내용', '옛 본문'),
                     self.page.replace('https://example.org/one', 'https://example.org/other')):
            with self.subTest(page=page), self.assertRaises(RuntimeError): self.call(page)

    def test_links_are_bound_to_their_own_articles(self):
        self.edition['items'].append({'id': 'two', 'title': '둘째 자료',
            'url': 'https://example.org/two', 'source_name': '둘째 매체',
            'bullets': ['둘째 본문 내용'], 'reason': '둘째 선정 근거'})
        page = self.page.replace('https://example.org/one', 'https://example.org/two')
        page = page.replace('</article>', '</article><article data-horizon-item="two">'
            '<a href="https://example.org/one">둘째 자료</a> 둘째 매체 둘째 본문 내용 둘째 선정 근거</article>')
        with self.assertRaises(RuntimeError): self.call(page)

    def test_missing_collection_source_fails(self):
        with self.assertRaises(RuntimeError):
            self.call(self.page.replace('https://example.org/feed', 'https://example.org/no-feed'))


class OptionalVerificationTests(unittest.TestCase):
    def test_horizon_failure_does_not_block_other_verified_content(self):
        from aidaily.publishing import daily, horizon_verification, youtube_verification, customer_verification
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'search-index.json').write_text(json.dumps([
                {'date': '2026-11-03', 'kind': 'ai_news', 'title': '오늘 뉴스'}]), encoding='utf-8')
            with patch.object(daily.config, 'DOCS_ROOT', root), \
                 patch.object(daily, 'horizon_enabled', return_value=True), \
                 patch.object(youtube_verification, 'verify_youtube_publication', return_value={'videos_verified': True}), \
                 patch.object(customer_verification, 'verify_customer_publication', return_value={'status': 'verified'}), \
                 patch.object(horizon_verification, 'verify_horizon_publication', side_effect=RuntimeError('stale')):
                result = daily.verify_publication('2026-11-03', attempts=1,
                    opener=lambda *args, **kwargs: Response('2026.11.03 오늘 뉴스'))
        self.assertTrue(result['headline_confirmed'])
        self.assertTrue(result['videos_verified'])
        self.assertEqual(result['horizon']['status'], 'verification_failed')
        self.assertTrue(result['horizon']['optional'])


if __name__ == '__main__': unittest.main()
