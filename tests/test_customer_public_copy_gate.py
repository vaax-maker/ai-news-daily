import importlib.util
import os
import unittest
if os.environ.get('PUBLIC_COPY_GATE_MODULE'):
    spec=importlib.util.spec_from_file_location('staged_copy_gate',os.environ['PUBLIC_COPY_GATE_MODULE'])
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
else:
    from aidaily.customer_stories import public_copy_gate as gate

class PublicCopyGateTests(unittest.TestCase):
    def report(self,text,key='overview'):
        report={'title':'현장 이야기','overview':'확인된 사실과 사용자의 경험','items':[{'issue':'음성 도구 비교','voices':[]}]}
        if key=='overview':report[key]=text
        else:report['items'][0]['voices']=[{'text':text,'source':'오픈채팅 · 모임 3'}]
        return report
    def dossier(self,text,private=True):return {'evidence':[{'text':text,'private':private,'evidence_id':'opaque-e1'}]}
    def test_private_copy_in_overview_or_voice_requires_review(self):
        private='한국어 음성인식 모델을 직접 실행했더니 배치 처리와 단일 처리의 속도 차이를 크게 느꼈습니다.'
        for key in ('overview','voice'):
            with self.subTest(key=key):
                with self.assertRaisesRegex(gate.PublicCopyReviewRequired,'possible_private_source_copy'):
                    gate.validate_public_copy(self.report('사용자는 '+private,key),self.dossier(private),allow_anonymous_quotes=False)
    def test_whitespace_and_punctuation_do_not_hide_a_copy(self):
        private='실제 사용 결과는 여러 조건에서 차이가 났고 다른 기능도 반복해서 점검했습니다.'
        copied=private.replace(' ',' / ')
        with self.assertRaises(gate.PublicCopyReviewRequired):gate.validate_public_copy(self.report(copied),self.dossier(private),allow_anonymous_quotes=False)
    def test_meaningful_short_whole_private_source_is_reviewed(self):
        source='배치처리에서는속도차이가거의없었다'
        with self.assertRaises(gate.PublicCopyReviewRequired):gate.validate_public_copy(self.report('그의 평가는 '+source+'는 것이었다.'),self.dossier(source),allow_anonymous_quotes=False)
    def test_anonymous_quote_is_allowed_by_default(self):
        private='돌려봤는데 정확도면에서 차이가 많이 나네요 그리고 위스퍼 배치연산을 돌리면'
        self.assertIsNone(gate.validate_public_copy(self.report(private),self.dossier(private)))
    def test_overt_identifiers_are_blocked_without_echoing_values(self):
        for value in ['contact@example.org','010-1234-5678','+82 10 1234 5678','02-1234-5678','@private_handle','방 ID: 18472466542857243','메시지id=123456','070-1234-5678','ｃｏｎｔａｃｔ＠ｅｘａｍｐｌｅ．ｏｒｇ']:
            with self.subTest(value=value):
                with self.assertRaises(gate.PublicCopyReviewRequired)as error:
                    gate.validate_public_copy(self.report('사용자 정보 '+value),{'evidence':[]})
                self.assertNotIn(value,str(error.exception))
    def test_product_versions_dates_and_paraphrase_are_allowed(self):
        report=self.report('2026-11-02에 Whisper large-v3와 STT-Ko-v1을 비교했다. 한국어 인식의 빠르기와 오류를 함께 살폈다.')
        self.assertIsNone(gate.validate_public_copy(report,self.dossier('원래의 사용자는 어떤 음성 입력을 썼는지 밝히지 않았고 설정의 비교 방법을 물었습니다.')))
    def test_links_and_evidence_ids_are_not_public_prose(self):
        report=self.report('공식 자료로 기능을 확인했다.')
        report['items'][0]['background']=[{'text':'기능 설명','label':'공식 안내','url':'https://example.org/contact@example.org/'}]
        report['items'][0]['evidence_ids']=['private@id:1234567890123']
        self.assertIsNone(gate.validate_public_copy(report,{'evidence':[]}))
    def test_public_source_copy_is_not_treated_as_private(self):
        text='이 공개 문장은 제품의 배치 처리 기능과 실행 환경에 관한 안내를 제공합니다.'
        self.assertIsNone(gate.validate_public_copy(self.report(text),self.dossier(text,False)))
    def test_source_labels_are_checked_and_invalid_inputs_fail_closed(self):
        report=self.report('일반적인 비교 관찰이다.','voice');report['items'][0]['voices'][0]['source']='연락처 contact@example.org'
        with self.assertRaises(gate.PublicCopyReviewRequired):gate.validate_public_copy(report,{'evidence':[]})
        with self.assertRaises(gate.PublicCopyReviewRequired):gate.validate_public_copy(self.report('평범한 문장입니다.'),{'evidence':[{'private':True}]})

if __name__=='__main__':unittest.main()
