import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aidaily.publishing import editorial


class DailyEditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / 'store.json'
        self.rows = [{'id': f'news:{n}', 'title': f'기사 {n}',
                      'summary_bullets': [f'주제 {n}의 실제 대표 문장입니다.']}
                     for n in range(4)]
        self.store.write_text(json.dumps(self.rows))
        self.result = {'items': [{'n': n, 'keyword': keyword, 'headline': '변화를 알아야 하는 이유', 'quote_index': 0}
                                 for n, keyword in enumerate(['AI신비주의', 'AI안경 길안내', 'AI도구명시 채용공고'])]}

    def prepare(self, date='2026-10-14', generate=None):
        with patch.object(editorial, '_visible', return_value=self.rows):
            return editorial.prepare(self.store, date, self.root, generate)

    def test_all_candidates_local_only_and_original_quote_selection(self):
        generate = Mock(return_value=self.result)
        chosen = self.prepare(generate=generate)
        args, kwargs = generate.call_args
        self.assertEqual(len(json.loads(args[1])['candidates']), 4)
        self.assertIs(kwargs['allow_external'], False)
        self.assertEqual(chosen['candidate_count'], 4)
        self.assertEqual(chosen['items'][1]['keyword'], 'AI안경 길안내')
        self.assertEqual(chosen['items'][1]['quote'], self.rows[1]['summary_bullets'][0])
        self.assertEqual(json.loads((self.root/'must-know/2026-10-14.json').read_text()), chosen)

    def test_same_edition_reuses_selection_without_model_call(self):
        self.prepare(generate=Mock(return_value=self.result))
        generate = Mock(side_effect=AssertionError('duplicate editorial request'))
        self.prepare(generate=generate)
        generate.assert_not_called()

    def test_manual_topics_preserved_and_archived(self):
        manual = {'date': '2026-10-13', 'items': [
            {'id': self.rows[n]['id'], 'keyword': '手動', 'headline': '제목', 'quote': self.rows[n]['summary_bullets'][0]}
            for n in range(3)]}
        (self.root/'today-must-know.json').write_text(json.dumps(manual))
        generate = Mock(side_effect=AssertionError('manual topics replaced'))
        self.assertEqual(self.prepare('2026-10-13', generate), manual)
        generate.assert_not_called()
        self.assertTrue((self.root/'must-know/2026-10-13.json').exists())

    def test_new_day_preserves_previous_day_archive(self):
        self.prepare('2026-10-13', Mock(return_value=self.result))
        old = (self.root/'must-know/2026-10-13.json').read_bytes()
        self.prepare('2026-10-14', Mock(return_value=self.result))
        self.assertEqual((self.root/'must-know/2026-10-13.json').read_bytes(), old)

    def test_duplicate_selection_does_not_write_publication_data(self):
        bad = {'items': [self.result['items'][0]]*3}
        with self.assertRaises(ValueError):
            self.prepare(generate=Mock(return_value=bad))
        self.assertFalse((self.root/'today-must-know.json').exists())
