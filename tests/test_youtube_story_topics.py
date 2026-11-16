"""Structure contracts; semantic chronology still requires source comparison."""
import unittest
from unittest import mock
from aidaily.youtube_summaries import analyzer


class StoryTopicTests(unittest.TestCase):
    def report(self, count):
        return {'headline': '영상 주제', 'card_summary': '사실 요약',
                'sections': [{'title': f'영상에서 다룬 주제 {i}',
                              'bullets': [f'주제 {i}의 실제 사실 하나', f'주제 {i}의 실제 사실 둘']}
                             for i in range(count)],
                'glossary': [{'term': f'용어 {i}', 'definition': f'원문상 뜻 {i}'} for i in range(3)]}

    def test_variable_topics_keep_all_titles_bullets_and_order(self):
        for count in (1, 3, 7, 8):
            with self.subTest(count=count):
                report = self.report(count)
                sections, glossary = report['sections'][:], report['glossary'][:]
                result = analyzer._validate_report(report)
                self.assertEqual(result['report_schema'], 'story_topics_v2')
                self.assertEqual(result['sections'], sections)
                self.assertEqual(result['glossary'], glossary)
                expected = [s['bullets'][i] for i in range(2) for s in sections][:4]
                self.assertEqual(result['body_bullets'], expected)
                self.assertEqual(result['overview'], result['body_bullets'])
                self.assertEqual(result['why_bullets'], sections[0]['bullets'][:2])

    def test_specific_strategy_bullets_are_derived_without_second_summary(self):
        report = self.report(2)
        report['sections'][1]['title'] = '에이전트 운영 전략과 비용'
        report['overview'] = ['원문에 없는 별도 요약']
        result = analyzer._validate_report(report)
        self.assertEqual(result['why_bullets'], report['sections'][1]['bullets'])
        self.assertNotIn('원문에 없는 별도 요약', result['overview'])

    def test_empty_generic_duplicate_and_thin_sections_rejected(self):
        for titles in ([], ['핵심 개요'], ['핵심 주장 / 논점 구조'],
                       ['왜 중요한가'], ['용어 사전'], ['같은 제목', '같은  제목']):
            with self.subTest(titles=titles):
                report = self.report(len(titles))
                for item, title in zip(report['sections'], titles):
                    item['title'] = title
                with self.assertRaises(RuntimeError):
                    analyzer._validate_report(report)
        report = self.report(1)
        report['sections'][0]['bullets'] = []
        with self.assertRaises(RuntimeError):
            analyzer._validate_report(report)
        report['sections'][0]['bullets'] = '문자열은 불릿 배열이 아님'
        with self.assertRaises(RuntimeError):
            analyzer._validate_report(report)

    def test_single_news_fact_can_stay_a_topic_without_padding(self):
        report = self.report(1)
        report['sections'][0]['bullets'] = ['원문의 단일 소식을 사실 그대로 전달한다.']
        self.assertEqual(analyzer._validate_report(report)['sections'][0]['bullets'], ['원문의 단일 소식을 사실 그대로 전달한다.'])

    def test_prompt_demands_source_order_and_merge_without_inventing(self):
        self.assertIn('전개되는 순서', analyzer.SYS)
        self.assertIn('가장 비중 있게 다룬 위치', analyzer.SYS)
        self.assertIn('하나로 합쳐', analyzer.SYS)
        self.assertIn('사실을 만들어 내지 않는다', analyzer.SYS)
        self.assertNotIn('len(sections) == 6', analyzer.SYS)

    def test_current_generation_rejects_one_line_explanations(self):
        report = self.report(1)
        with self.assertRaisesRegex(RuntimeError, '설명 부족'):
            analyzer._validate_report(report, require_explanations=True)
        report['sections'][0]['bullets'] = ['클라우드 에이전트는 원격 작업 공간에서 화면을 보고 요청한 작업을 수행하며, 사람이 제공한 목표와 자료를 이용한다. 결과 화면을 확인한 뒤 원하는 모습과 차이가 있으면 다시 수정하고 확인하는 작업 흐름을 설명한다.']
        result = analyzer._validate_report(report, require_explanations=True)
        self.assertEqual(result['explanation_style'], 'contextual_bullets_v2')
        result['sections'][0]['bullets'] = ['12.5% 수치 하나만 전달한다.']
        with self.assertRaisesRegex(RuntimeError, '설명 부족'):
            analyzer._validate_report(result)

    def test_distinct_points_stay_separate_instead_of_a_long_bullet(self):
        report = self.report(1)
        first = '클라우드 에이전트는 사용자가 목표를 전달하면 원격 작업 공간에 연결되어 실행하며, 도구를 이용해 그 목표를 수행한다.'
        second = '화면을 보고 마우스와 키보드를 조작하는 컴퓨터 유즈는 작업 결과를 다시 확인하고 수정하는 과정에도 사용된다.'
        report['sections'][0]['bullets'] = [first, second]
        result = analyzer._validate_report(report, require_explanations=True)
        self.assertEqual(result['sections'][0]['bullets'], [first, second])
        report['sections'][0]['bullets'] = [first + ' ' + second + ' ' + first]
        with self.assertRaisesRegex(RuntimeError, '과도한 묶음'):
            analyzer._validate_report(report, require_explanations=True)

    def test_long_input_selected_quotes_are_sent_in_source_order(self):
        quotes = [{'id': 'S2', 'start': 9000, 'end': 9010, 'quote': '후반 근거', 'topic': '뒷부분'},
                  {'id': 'S1', 'start': 100, 'end': 110, 'quote': '앞부분 근거', 'topic': '앞부분'}]
        analysis = self.report(1)
        analysis['sections'][0]['bullets'] = ['클라우드 에이전트는 원격 작업 공간에서 화면을 보고 요청한 작업을 수행하며, 이 과정은 사람이 제공한 목표와 자료를 바탕으로 진행된다. 결과 화면을 확인한 뒤 원하는 모습과 차이가 있으면 다시 수정하는 흐름을 설명한다.']
        source_info = {'source_characters': 16000, 'chunks': [], 'source_sha256': 'test'}
        with mock.patch('aidaily.youtube_summaries.source_chunks.extract', return_value=(quotes, source_info)), \
             mock.patch('aidaily.youtube_summaries.source_chunks.bounded_notes', return_value=quotes), \
             mock.patch('aidaily.youtube_summaries.resilient_llm.complete_json', return_value=analysis) as generate:
            result = analyzer.analyze('a' * 16000, title='영상', channel='채널')
        user = generate.call_args.args[1]
        self.assertLess(user.index('S1'), user.index('S2'))
        self.assertEqual([q['id'] for q in result['source_analysis']['selected_quotes']], ['S1', 'S2'])
        self.assertEqual(result['source_analysis']['selected_quotes'][0]['topic'], '앞부분')


if __name__ == '__main__':
    unittest.main()
