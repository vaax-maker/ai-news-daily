import json
import tempfile
import unittest
from pathlib import Path
from aidaily.customer_stories.story_pipeline import prepare,validate_report
from unittest import mock

class StoryPipelineTests(unittest.TestCase):
    def test_process_prose_does_not_replace_the_actual_experience(self):
        report=self.report()
        report['items'][0]['voices'][0]['text']='사용 경험이 발행 자료에 담겼다.'
        with self.assertRaisesRegex(ValueError,'experience directly'):
            validate_report(report,self.dossier(True))
    def test_existing_renderer_dispatch_and_archive_generation_blocks_model(self):
        from aidaily.customer_stories.pipeline import render_customer_stories
        from aidaily.customer_stories.story_pipeline import generate_story_report
        page=render_customer_stories({'schema_version':2,'title':'날짜 기사','items':[]},'2026-11-02')
        self.assertIn('날짜 기사',page)
        with mock.patch('aidaily.integrations.openrouter.complete') as model:
            with self.assertRaises(ValueError):generate_story_report(self.dossier())
            model.assert_not_called()
    def test_archive_revision_cannot_accidentally_enable_publication(self):
        report=self.report()
        with self.assertRaises(ValueError):validate_report(report,self.dossier(),archive_review=True)
        report['publication_allowed']=False
        self.assertIs(validate_report(report,self.dossier(),archive_review=True),report)
    def test_missing_dates_and_prior_publication_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'2026-11-02.json'
            path.write_text(json.dumps({'gen':{'items':[{'issue':'사례','content':'사용자가 기능을 실행했다.','sources':['Reddit'],'publication_index':17}]}}))
            result=prepare(folder,'2026-11-02',2)
            self.assertEqual(result['missing_dates'],['2026-11-01'])
            self.assertEqual(result['evidence'][0]['publication_id'],'customer_story:2026-11-02:17')
            self.assertFalse(result['publication_allowed'])
            self.assertIsNone(result['conversation_share'])
            self.assertEqual(result['evidence'][0]['evidence_id'],prepare(folder,'2026-11-02',2)['evidence'][0]['evidence_id'])
    def dossier(self,new=False):
        return {'evidence':[{'evidence_id':'e1','already_published':not new,'url':'https://example.org/a'}]}
    def report(self):
        return {'items':[{'story_id':'story-a','evidence_ids':['e1'],'voices':[{'text':'사례','evidence_ids':['e1']}]}]}
    def test_recycled_story_and_unknown_citation_blocked(self):
        with self.assertRaisesRegex(ValueError,'no new evidence'):validate_report(self.report(),self.dossier())
        report=self.report();report['items'][0]['evidence_ids']=['unknown']
        with self.assertRaises(ValueError):validate_report(report,self.dossier(True))
    def test_background_and_individual_claims_need_evidence(self):
        report=self.report();report['items'][0]['background']=[{'text':'사실','url':'https://invented.example/'}]
        with self.assertRaises(ValueError):validate_report(report,self.dossier(True))
        report=self.report();report['items'][0]['voices'][0]['evidence_ids']=[]
        with self.assertRaises(ValueError):validate_report(report,self.dossier(True))
    def test_repeat_story_id_and_fabricated_url_blocked(self):
        with self.assertRaises(ValueError):validate_report(self.report(),self.dossier(True),history=['story-a'])
        report=self.report();report['items'][0]['related_links']=[{'url':'https://invented.example/'}]
        with self.assertRaises(ValueError):validate_report(report,self.dossier(True))
    def test_supplied_research_and_new_evidence_pass_structural_gate_only(self):
        report=self.report();report['items'][0]['background']=[{'text':'자료에 따른 배경','url':'https://example.org/research'}]
        self.assertIs(validate_report(report,self.dossier(True),[{'url':'https://example.org/research'}]),report)

if __name__=='__main__':unittest.main()
