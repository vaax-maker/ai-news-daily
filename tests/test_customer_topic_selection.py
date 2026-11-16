import unittest
from uuid import UUID
from aidaily.customer_stories.topic_selection import SelectionConfig, SelectionInputError, select_topics


def uid(n):
    return str(UUID(int=(4 << 76) | (2 << 62) | n))


def receipt(n, ids):
    return {'source_id': uid(n), 'complete': True, 'message_ids': ids,
            'unit': 'message', 'window_start': '2026-11-01T00:00:00+09:00',
            'window_end': '2026-11-02T00:00:00+09:00'}


def reviewed(topics=()):
    return {'status': 'reviewed', 'topic_ids': list(topics)}


class TopicSelectionTests(unittest.TestCase):
    def sample(self):
        sources = [receipt(101,[uid(i) for i in range(1,6)]),
                   receipt(102,[uid(i) for i in range(6,11)])]
        assignments = {uid(i): reviewed([uid(201)] if i in (1,2,6) else [])
                       for i in range(1,11)}
        return sources, assignments

    def test_exact_thirty_percent_and_audit(self):
        sources, rows = self.sample(); result = select_topics(sources, rows)
        self.assertEqual(result['selected_topic_ids'], [uid(201)])
        row = result['topics'][0]
        self.assertEqual((row['message_count'], row['denominator']), (3,10))
        self.assertEqual(row['source_counts'][uid(101)], {'count':2,'denominator':5})
        self.assertEqual(row['qualifying_sources'], [uid(101)])
        self.assertEqual(result['unit'], 'message')
        self.assertEqual(result['window_start'], '2026-10-31T15:00:00+00:00')

    def test_below_overall_threshold_and_small_source(self):
        sources, rows = self.sample(); rows[uid(6)] = reviewed()
        result = select_topics(sources, rows)
        self.assertEqual(result['selection_status'], 'no_eligible_topics')
        self.assertIn('below_overall_threshold', result['topics'][0]['ineligibility_reasons'])
        sources = [receipt(101,[uid(1),uid(2)]), receipt(102,[uid(i) for i in range(3,11)])]
        rows = {uid(i): reviewed([uid(201)] if i in (1,2,3) else []) for i in range(1,11)}
        self.assertIn('no_qualifying_source', select_topics(sources, rows)['topics'][0]['ineligibility_reasons'])

    def test_multi_topic_and_stable_tie_cap(self):
        sources, rows = self.sample()
        for i in (1,2,6): rows[uid(i)] = reviewed([uid(203),uid(201),uid(202)])
        self.assertEqual(select_topics(sources, rows)['selected_topic_ids'], [uid(201),uid(202)])
        self.assertEqual(select_topics(sources, rows, SelectionConfig(maximum_topics=1))['selected_topic_ids'], [uid(201)])

    def test_incomplete_duplicate_unknown_and_classification_fail_closed(self):
        sources, rows = self.sample(); sources[0]['complete'] = False
        with self.assertRaises(SelectionInputError) as error: select_topics(sources, rows)
        self.assertNotIn(uid(101), str(error.exception))
        sources, rows = self.sample(); del rows[uid(1)]
        with self.assertRaises(SelectionInputError): select_topics(sources, rows)
        sources, rows = self.sample(); rows[uid(11)] = reviewed()
        with self.assertRaises(SelectionInputError): select_topics(sources, rows)
        sources, rows = self.sample(); sources[1]['message_ids'][0] = uid(1)
        with self.assertRaises(SelectionInputError): select_topics(sources, rows)
        with self.assertRaises(SelectionInputError): select_topics([receipt(101,[])], {})
        for status in ('failed', 'unreviewed', None):
            sources, rows = self.sample(); rows[uid(1)]['status'] = status
            with self.subTest(status=status), self.assertRaises(SelectionInputError): select_topics(sources, rows)

    def test_units_windows_and_sensitive_identifier_rejected(self):
        for key, value in [('unit', 'post'), ('unit', None),
                           ('window_start', '2026-11-01T00:00:00'),
                           ('window_start', '2026-11-02T00:00:00+09:00'),
                           ('window_end', '2026-11-03T00:00:00+09:00'),
                           ('source_id', 'private-group-name')]:
            sources, rows = self.sample(); sources[1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(SelectionInputError) as error:
                select_topics(sources, rows)
            self.assertNotIn('private-group-name', str(error.exception))
        sources, rows = self.sample()
        sources[1]['window_start'] = '2026-10-31T15:00:00Z'
        sources[1]['window_end'] = '2026-11-01T15:00:00Z'
        self.assertEqual(select_topics(sources, rows)['selected_topic_ids'], [uid(201)])

    def test_config_validation_duplicate_assignment_and_no_topics(self):
        sources, rows = self.sample()
        for value in ('NaN', '1.01', '-0.1', True):
            with self.subTest(value=value), self.assertRaises(SelectionInputError):
                select_topics(sources, rows, SelectionConfig(overall_minimum=value))
        with self.assertRaises(SelectionInputError): select_topics(sources, rows, SelectionConfig(maximum_topics=3))
        rows[uid(1)] = reviewed([uid(201),uid(201)])
        with self.assertRaises(SelectionInputError): select_topics(sources, rows)
        sources, rows = self.sample(); rows = {key: reviewed() for key in rows}
        self.assertEqual(select_topics(sources, rows)['selection_status'], 'no_classified_topics')

if __name__ == '__main__': unittest.main()
