import unittest
from copy import deepcopy
from aidaily.customer_stories.editorial_selection import EditorialConfig,EditorialInputError,evaluate_candidates

class EditorialRulesTests(unittest.TestCase):
    def topic(self):
        return {'topic_id':'grok-bot','observations':[
          {'evidence_id':'e1','date':'2026-10-23','source_id':'room-1','kind':'question'},
          {'evidence_id':'e2','date':'2026-10-27','source_id':'room-1','kind':'question'}],
          'research':[{'url':'https://x.ai/news/introducing-grok-bot','verified':True,'primary':True}],
          'already_reported':False,'new_development':False}
    def test_repeated_question_becomes_explainer_without_thirty_percent(self):
        r=evaluate_candidates([self.topic()]);self.assertEqual(r['selected_topic_ids'],['grok-bot'])
        self.assertEqual(r['candidates'][0]['article_kind'],'explainer');self.assertFalse(r['publication_allowed'])
    def test_oneoff_promotions_and_unverified_research_do_not_qualify(self):
        for change in ('oneoff','promotion','unverified','secondary'):
            t=self.topic()
            if change=='oneoff':t['observations']=t['observations'][:1]
            if change=='promotion':
                for o in t['observations']:o['kind']='promotion'
            if change=='unverified':t['research'][0]['verified']=False
            if change=='secondary':t['research'][0]['primary']=False
            with self.subTest(change=change):self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],[])
    def test_two_sources_same_day_and_tunable_threshold(self):
        t=self.topic();t['observations'][1].update(date='2026-10-23',source_id='room-2')
        self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],['grok-bot'])
        self.assertEqual(evaluate_candidates([t],EditorialConfig(minimum_days=3,minimum_sources=3))['selected_topic_ids'],[])
    def test_duplicate_evidence_and_bad_inputs_fail_closed(self):
        for field,value in [('date','2026-13-01'),('source_id','개인 이름'),('kind','rumor')]:
            t=self.topic();t['observations'][0][field]=value
            with self.subTest(field=field),self.assertRaises(EditorialInputError):evaluate_candidates([t])
        t=self.topic();t['observations'][1]['evidence_id']='e1'
        with self.assertRaises(EditorialInputError):evaluate_candidates([t])
        t=self.topic();t['research'][0]['url']='javascript:alert(1)'
        with self.assertRaises(EditorialInputError):evaluate_candidates([t])
    def test_prior_report_requires_explicit_unpublished_evidence(self):
        t=self.topic();t.update(already_reported=True,new_development=True,new_evidence_ids=['e2'])
        self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],[])
        t['observations'][1]['already_published']=False
        self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],['grok-bot'])
        t['new_development']=False
        self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],[])
    def test_experience_is_distinct_and_maximum_two(self):
        t=self.topic();t['observations']=t['observations'][:1];t['observations'][0]['kind']='experience'
        self.assertEqual(evaluate_candidates([t])['candidates'][0]['article_kind'],'experience')
        t['research']=[];self.assertEqual(evaluate_candidates([t])['selected_topic_ids'],[])
        topics=[]
        for n in range(3):
            a=self.topic();a['topic_id']='topic-'+str(n)
            for o in a['observations']:o['evidence_id']+=str(n)
            topics.append(a)
        self.assertEqual(len(evaluate_candidates(topics)['selected_topic_ids']),2)

if __name__=='__main__':unittest.main()
