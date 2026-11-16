import unittest
from unittest import mock
from aidaily.ai_news import extra_sources as extra

class ConfiguredSourceLimitTests(unittest.TestCase):
    def rows(self, limit):
        return [{'id':'fixture','name':'AI타임스','url':'https://fixture.invalid/rss','connector':'rss','limit_mode':'fixed','limit':limit}]
    def rss(self):
        return ('<rss><channel>'+''.join(f'<item><title>인공지능 모델 기술 공개 {n}</title><link>https://fixture.invalid/{n}</link><description>모델 연구 성능</description></item>' for n in range(7))+'</channel></rss>').encode()
    def test_fixed_three_and_five_actual_selection_and_merge(self):
        for limit in (3,5):
            with self.subTest(limit=limit), mock.patch.object(extra.content_settings,'sources',return_value=self.rows(limit)), mock.patch.object(extra.content_settings,'load',return_value={}), mock.patch.object(extra,'_get',return_value=self.rss()), mock.patch.object(extra,'_summarize_ko',side_effect=lambda a:{'headline':a['title'],'body':a['body'],'takeaway':'fixture'}):
                self.assertEqual(len(extra.fetch_extra()),limit)
                result=extra.merge_into({'date':'2026-10-13','stories':[]},use_seen_store=False)
                self.assertEqual(len(result['stories']),limit)
                self.assertEqual([s['n'] for s in result['stories']],[f'{n:02d}' for n in range(1,limit+1)])
    def test_restored_five_and_aiofmodu_all_preserved(self):
        today={'date':'2026-10-13','stories':[{'source':'aiofmodu','headline':f'curated {n}','url':f'a{n}'} for n in range(6)]+[{'source':'AI타임스','headline':f'restored {n}','url':f'r{n}'} for n in range(5)]}
        with mock.patch.object(extra.content_settings,'sources',return_value=self.rows(5)), mock.patch.object(extra.content_settings,'load',return_value={}), mock.patch.object(extra,'fetch_extra',return_value=[]) as fetch:
            result=extra.merge_into(today,use_seen_store=False)
        self.assertEqual(len(result['stories']),11)
        self.assertEqual(fetch.call_args.kwargs['limit_per_source'],{'AI타임스':0})
    def test_env_limits_are_not_capped(self):
        parsed=extra._parse_limits('MIT Tech Review:3,CB Insights:5')
        self.assertEqual(parsed['MIT Tech Review'],3)
        self.assertEqual(parsed['CB Insights'],5)
