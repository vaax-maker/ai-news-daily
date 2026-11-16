import unittest
from aidaily.customer_stories.story_render import render_story_report, safe_url, story_anchor


class StoryRenderTests(unittest.TestCase):
    def story(self, identity='a'):
        return {'story_id': identity, 'issue': '모델의 실제 사용 조건',
                'background': [{'text': '공개 안내 내용', 'url': 'https://example.org/facts?a=1&b=2', 'label': '공개 근거'}],
                'voices': [{'text': '특정 조건에서 관찰한 결과', 'source': '오픈채팅 · 모임 3', 'date': '2026-11-02'}],
                'timeline': [{'stage': '시도', 'text': '사용자가 시도한 내용', 'evidence_ids': ['opaque']}],
                'commentary': '확인된 조건 안에서 해석한다.'}

    def test_two_stories_have_stable_targets_and_attribution(self):
        a, b = self.story('a'), self.story('b')
        result = render_story_report({'items': [a, b]}, '2026-11-02')
        self.assertEqual(result.count('<article '), 2)
        self.assertIn('확인된 사실', result)
        self.assertIn('사용자 목소리', result)
        self.assertIn('오픈채팅 · 모임 3', result)
        self.assertIn(f'href="#{story_anchor("b")}"', result)
        self.assertIn(f'id="{story_anchor("b")}"', result)
        reverse = render_story_report({'items': [b, a]}, '2026-11-02')
        self.assertIn(f'id="{story_anchor("b")}"', reverse)
        self.assertIn('href="index.html"', result)

    def test_script_and_attributes_are_escaped_and_invalid_facts_hidden(self):
        row = self.story()
        row['issue'] = '<script>alert(1)</script>'
        row['background'] = [{'text': 'unsupported dangerous fact', 'url': 'javascript:alert(1)'}]
        row['voices'][0]['text'] = '<img src=x onerror=alert(1)>'
        row['related_links'] = [{'url': 'https://example.org/"x', 'label': '<svg onload=alert(1)>'}]
        page = render_story_report({'items': [row]}, '<script>date</script>')
        self.assertNotIn('<script>', page)
        self.assertNotIn('<img', page)
        self.assertNotIn('javascript:', page)
        self.assertNotIn('unsupported dangerous fact', page)
        self.assertIn('확인된 공개 배경 자료가 없습니다.', page)
        self.assertIn('&lt;svg', page)
        self.assertIn('&quot;x', page)

    def test_url_policy_rejects_credentials_controls_malformed_port(self):
        for url in ['//example.org/a', 'data:text/plain,x', 'file:///tmp/a', 'https://u:p@example.org',
                    'https://example.org:bad', 'https://example.org/a\nb', ' https://example.org']:
            self.assertEqual(safe_url(url), '', url)
        self.assertEqual(safe_url('https://example.org/a#b'), 'https://example.org/a#b')

    def test_empty_and_unsupported_timeline_do_not_create_evidence(self):
        row = self.story(); row['timeline'] = [{'text': 'no evidence', 'stage': '결과'}]
        row['voices'] = []
        page = render_story_report({'items': [row]}, '2026-11-02')
        self.assertNotIn('no evidence', page)
        self.assertIn('확인 가능한 사용자 경험이 없습니다.', page)
        empty = render_story_report({'items': []}, '2026-11-02')
        self.assertIn('선정된 이야기가 없습니다.', empty)
        self.assertNotIn('<article ', empty)

    def test_duplicate_identity_bad_version_and_overflow_fail(self):
        for report in [{'items': [self.story(), self.story()]}, {'items': [self.story(str(i)) for i in range(3)]},
                       {'schema_version': 1, 'items': []}, {'items': [{'issue': 'missing id'}]}]:
            with self.assertRaises(ValueError): render_story_report(report, '2026-11-02')
        with self.assertRaises(ValueError):
            render_story_report({'items': []}, '2026-11-02', archive_href='javascript:bad')


if __name__ == '__main__': unittest.main()
