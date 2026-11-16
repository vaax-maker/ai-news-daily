import unittest
from unittest.mock import patch
from aidaily.customer_stories import knowledge_filter as k,pipeline

class PrivateChatExceptionTests(unittest.TestCase):
    def row(self,content,kind='method'):
        return {'issue':'정보','content':content,'sources':['오픈채팅 · 방A (비공개 대화)'],'refs':[], '_knowledge':{'kind':kind,'source_excerpt':''}}
    def test_private_information_does_not_need_literal_source_or_link(self):
        row=self.row('RTX 3060에서 음성 인식을 처리하고 LLM API를 연결하는 방법이 안내됐습니다.')
        result=k.classify_item(row,'',True)
        self.assertTrue(result['keep']);self.assertEqual(result['reason'],'private_chat_source_exception')
    def test_private_items_with_empty_quotes_are_not_all_deduplicated(self):
        rows=[self.row('서버 설치 방법이 안내됐습니다.'),self.row('메신저 연결 방법이 안내됐습니다.')]
        result=k.filter_report({'items':rows},'',True)
        self.assertEqual(len(result['items']),2);self.assertEqual([x['publication_index'] for x in result['items']],[0,1])
    def test_questions_reactions_requests_remain_excluded(self):
        for text,kind in [('어떻게 설치하는지 궁금하다고 물었다.','answer'),('정말 좋다는 평가입니다.','observed_result'),('간단한 업데이트 명령을 요청했습니다.','feature')]:
            self.assertFalse(k.classify_item(self.row(text,kind),'',True)['keep'])
    def test_web_refs_and_mixed_sources_do_not_get_exemption(self):
        row=self.row('설치 방법이 안내됐다.');row['refs']=['R1'];self.assertFalse(k.classify_item(row,'',True)['keep'])
        row=self.row('설치 방법이 안내됐다.');row['sources'].append('Reddit');self.assertFalse(k.private_chat_exception(row))
    def test_judge_receives_exception_and_item_numbers_are_exempt(self):
        gen={'items':[self.row('RTX 3060에서 실행한 결과를 공유했다.','observed_result')]}
        self.assertEqual(pipeline.evidence_issues(gen,''),[])
        with patch.object(pipeline,'_llm_complete',return_value='{"ok":true,"fabrication":false,"pii":false,"knowledge":true,"issues":[]}') as call:
            pipeline.judge(gen,'');self.assertIn('private_chat_exception',call.call_args.args[1])
    def test_private_exception_cannot_be_rejected_again_by_source_judge(self):
        gen={'items':[self.row('RTX 3060에서 음성 인식을 실행한 결과를 공유했다.','observed_result')],'_knowledge_policy':1}
        with patch.object(pipeline,'judge',side_effect=AssertionError('chat source judge must not run')):
            result=pipeline.evaluate(gen,'')
        self.assertTrue(result['passed']);self.assertEqual(result['source_verification'],'exempt_private_chat')
