import unittest
from unittest import mock
from aidaily.customer_stories import knowledge_filter as k,pipeline
from aidaily.integrations import openrouter

class KnowledgeTests(unittest.TestCase):
    def item(self,content,excerpt=None):
        row={'issue':'설정 질문','content':content,'sources':['방A'],'refs':[]}
        if excerpt is not None:row['_knowledge']={'kind':'answer','source_excerpt':excerpt}
        return row
    def corpus(self):
        return '===== [오픈채팅 · 방A (비공개 대화)] =====\n오프라인 전사가 가능한가요?\n설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.\n===== [오픈채팅 · 방B (비공개 대화)] =====\n외부 API를 연결하면 모델 교체가 가능합니다.'
    def test_question_with_source_answer_survives_question_title(self):
        row=self.item('오프라인 전사가 가능한지 질문했고, 설정에서 로컬 모델을 설치하는 방법이 안내됐다.','설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.')
        self.assertTrue(k.classify_item(row,self.corpus(),True)['keep'])
    def test_unanswered_question_and_wish_or_reaction_are_removed(self):
        for content in ['오프라인 전사가 가능한지 궁금하다고 물었다.','강력한 로컬 모델을 쓸 날이 기대된다는 반응이 나왔다.','영상 만들기가 재미있다는 반응과 포인트 소진이 빠르다는 반응도 나왔다.']:
            with self.subTest(content=content):self.assertFalse(k.classify_item(self.item(content),self.corpus())['keep'])
    def test_answer_must_come_from_same_room_not_generated_summary(self):
        for excerpt in ['모든 영상은 제한 없이 생성됩니다.','외부 API를 연결하면 모델 교체가 가능합니다.','오프라인 전사가 가능한가요?']:
            row=self.item('오프라인 전사 설정 방법이 안내됐다.',excerpt)
            self.assertFalse(k.classify_item(row,self.corpus(),True)['keep'])
    def test_web_refs_scope_is_literal_and_missing_quote_blocks_new_policy(self):
        row={'issue':'로컬 전사','content':'오프라인 전사 방법이 안내됐다.','sources':['웹'],'refs':['R1'],'_knowledge':{'kind':'method','source_excerpt':'설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.'}}
        self.assertTrue(k.classify_item(row,'[R1] 설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.',True)['keep'])
        self.assertFalse(k.classify_item(row,'[R2] 설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.',True)['keep'])
        row.pop('_knowledge');self.assertFalse(k.classify_item(row,'[R1] 설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.',True)['keep'])
    def test_stable_original_index_and_original_report_are_preserved(self):
        gen={'title':'질문','overview':'질문만','items':[self.item('궁금하다고 물었다.'),self.item('설정 방법이 안내됐다.','설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.')]}
        filtered=pipeline.apply_knowledge_gate(gen,self.corpus())
        self.assertEqual(len(filtered['items']),1);self.assertEqual(filtered['items'][0]['publication_index'],1)
        self.assertEqual(len(gen['items']),2);self.assertNotIn('질문만',filtered['overview'])
        self.assertNotIn(filtered['items'][0]['issue'],filtered['overview'])
        again=pipeline.apply_knowledge_gate(filtered,self.corpus());self.assertEqual(again['items'][0]['publication_index'],1)
    def test_empty_information_blocks_publication(self):
        with self.assertRaises(openrouter.RoutingBlocked):pipeline.apply_knowledge_gate({'items':[self.item('궁금하다고 물었다.')]},self.corpus())
    def test_semantic_judge_cannot_accept_unanswered_question(self):
        gen={'items':[self.item('궁금하다고 물었다.')]}
        with mock.patch.object(pipeline,'judge',return_value={'ok':True,'fabrication':False,'pii':False,'knowledge':True}):
            self.assertFalse(pipeline.evaluate(gen,self.corpus())['passed'])

class LiteralDuplicateTests(unittest.TestCase):
    def test_only_identical_information_excerpt_is_deduplicated(self):
        quote='설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.'
        rows=[{'issue':str(i),'content':'설정 방법이 안내됐다.','sources':['방A'],'_knowledge':{'kind':'method','source_excerpt':quote}} for i in range(2)]
        corpus='===== [오픈채팅 · 방A (비공개 대화)] =====\n'+quote
        result=k.filter_report({'items':rows},corpus)
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['_knowledge_gate']['decisions'][1]['reason'],'duplicate_literal_information_evidence')

class RunKnowledgePublicationTests(unittest.TestCase):
    def run_saved(self,gen,corpus,root):
        import argparse
        from aidaily.customer_stories import checkpoint
        args=argparse.Namespace(date='2026-10-13',docs_root=root+'/docs')
        with checkpoint.locked(root,args.date) as saved:
            saved.save(stage='ready',date=args.date,gen=gen,inputs={'corpus':corpus,'active':['방A'],'new_urls':[],'refmap':{},'new_msg_hashes':[]})
            before=saved.path.read_bytes()
            with mock.patch.object(pipeline,'load_seen',return_value={}):
                try:pipeline._run(args,root,saved)
                except SystemExit as error:
                    return error.code,before,saved.path.read_bytes(),saved.state
        self.fail('pipeline should skip publication')
    def test_empty_information_exit_two_preserves_original_fields_and_no_public_files(self):
        import tempfile
        from pathlib import Path
        gen={'title':'질문','overview':'질문','items':[{'issue':'질문','content':'사용 방법이 궁금하다고 물었다.','sources':['방A']}],'_eval':{'passed':True}}
        with tempfile.TemporaryDirectory() as root:
            code,before,after,state=self.run_saved(gen,'===== [오픈채팅 · 방A (비공개 대화)] =====\n사용 방법이 궁금합니다?',root)
            self.assertEqual(code,2)
            import json
            previous=json.loads(before);current=json.loads(after)
            self.assertEqual(previous['inputs'],current['inputs']);self.assertEqual(previous['gen'],current['gen'])
            self.assertEqual(state['stage'],'complete');self.assertEqual(state['status'],'no_information')
            self.assertFalse(Path(root+'/docs').exists());self.assertFalse(Path(root+'/latest.json').exists())
    def test_new_policy_failed_evaluation_stays_review_and_does_not_publish(self):
        import tempfile
        from pathlib import Path
        quote='설정에서 로컬 모델을 설치하면 오프라인 전사가 가능합니다.'
        gen={'title':'정보','overview':'설정 방법','items':[{'issue':'설정 방법','content':'설정 방법이 안내됐다.','sources':['방A'],'_knowledge':{'kind':'method','source_excerpt':quote}}],'_knowledge_policy':1,'_eval':{'passed':False}}
        with tempfile.TemporaryDirectory() as root:
            code,before,after,state=self.run_saved(gen,'===== [오픈채팅 · 방A (비공개 대화)] =====\n'+quote,root)
            self.assertEqual(code,2);self.assertEqual(state['stage'],'review')
            self.assertEqual(state['gen']['items'][0]['content'],gen['items'][0]['content'])
            self.assertFalse(Path(root+'/docs').exists());self.assertFalse(Path(root+'/latest.json').exists())
