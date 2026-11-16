import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

if os.environ.get('ROLLING_INPUTS_MODULE'):
    spec=importlib.util.spec_from_file_location('rolling_inputs_staged',os.environ['ROLLING_INPUTS_MODULE'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
    from aidaily.customer_stories import rolling_inputs as module

class RollingInputsTests(unittest.TestCase):
    def test_generated_v2_snapshot_is_not_a_confirmed_publication(self):
        with tempfile.TemporaryDirectory()as root:
            self.checkpoint(root,'2026-11-02','===== [오픈채팅 · 모임 1 (비공개 대화)] =====\n개인 비서가 어떤 작업을 하는지 궁금하다는 질문입니다.')
            before=module.gather(root,'2026-11-02',1);eid=before['evidence'][0]['evidence_id']
            Path(root,'2026-11-02.json').write_text(json.dumps({'gen':{'schema_version':2,'items':[{'story_id':'new-story','issue':'비서의 쓰임','voices':[],'evidence_ids':[eid]}]}}))
            folder=Path(root)/'newsroom';folder.mkdir();ledger=folder/'story-history.json'
            ledger.write_text(json.dumps([{'date':'2026-11-02','story_id':'new-story','status':'generated'}]))
            pending=module.gather(root,'2026-11-02',1)
            self.assertFalse(pending['evidence'][0]['already_published'])
            self.assertEqual(pending['history'][0]['status'],'generated')
            ledger.write_text(json.dumps([{'date':'2026-11-02','story_id':'new-story','status':'published'}]))
            self.assertTrue(module.gather(root,'2026-11-02',1)['evidence'][0]['already_published'])
    def checkpoint(self,root,day,corpus,refmap=None,stage='complete'):
        path=Path(root)/'checkpoints'/(day+'.json');path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'stage':stage,'inputs':{'corpus':corpus,'refmap':refmap or {}}},ensure_ascii=False))
    def test_stable_dedup_retains_observation_dates_not_message_count(self):
        with tempfile.TemporaryDirectory()as root:
            line='한국어 음성인식 도구의 처리 조건을 비교하는 질문입니다.'
            self.checkpoint(root,'2026-11-01','===== [오픈채팅 · 모임 3 (비공개 대화)] =====\n'+line+'\n'+line)
            self.checkpoint(root,'2026-11-02','===== [오픈채팅 · 모임 3 (비공개 대화)] =====\n'+line)
            dossier=module.gather(root,'2026-11-02',2)
            self.assertEqual(len(dossier['evidence']),1)
            row=dossier['evidence'][0]
            self.assertEqual(row['observed_dates'],['2026-11-01','2026-11-02'])
            self.assertEqual(row['evidence_id'],module.gather(root,'2026-11-02',1)['evidence'][0]['evidence_id'])
            self.assertFalse(dossier['coverage']['complete'])
            self.assertIsNone(dossier['coverage']['conversation_share'])
    def test_identical_text_across_sources_remains_separate(self):
        with tempfile.TemporaryDirectory()as root:
            dossier=module.gather(root,'2026-11-02',1,extra_rooms={'오픈채팅 · 모임 1':'같은 문장이지만 출처는 다른 사용 사례입니다.','오픈채팅 · 모임 2':'같은 문장이지만 출처는 다른 사용 사례입니다.'})
            self.assertEqual(len(dossier['evidence']),2)
            self.assertEqual(len({x['source_id']for x in dossier['evidence']}),2)
    def test_public_refs_and_prior_publication_are_linked(self):
        with tempfile.TemporaryDirectory()as root:
            corpus='===== [Hacker News (개발자)] =====\n[H1] A report describes a concrete software installation failure.'
            self.checkpoint(root,'2026-11-01',corpus,{'H1':{'url':'https://news.ycombinator.com/item?id=1'}})
            Path(root,'2026-11-01.json').write_text(json.dumps({'gen':{'items':[{'issue':'설치 문제','content':'설치 스크립트가 작동하지 않는 사례다.','sources':['Hacker News'],'refs':['H1'],'publication_index':4,'primary_url':'https://news.ycombinator.com/item?id=1'}]}}))
            dossier=module.gather(root,'2026-11-02',2)
            row=dossier['evidence'][0]
            self.assertEqual(row['source'],'HN');self.assertFalse(row['private'])
            self.assertEqual(row['url'],'https://news.ycombinator.com/item?id=1')
            self.assertTrue(row['already_published'])
            self.assertEqual(row['used_by_publication_ids'],['customer_story:2026-11-01:4'])
            self.assertEqual(dossier['history'][0]['evidence_ids'],[row['evidence_id']])
    def test_new_observation_on_previously_cited_url_is_not_automatically_recycled(self):
        with tempfile.TemporaryDirectory()as root:
            url='https://example.org/ongoing-story'
            self.checkpoint(root,'2026-11-01','===== [Hacker News (개발자)] =====\n[H1] An earlier observation describes a failed installation.',{'H1':{'url':url}})
            self.checkpoint(root,'2026-11-02','===== [Hacker News (개발자)] =====\n[H2] A genuinely different update describes a recovered installation.',{'H2':{'url':url}})
            Path(root,'2026-11-01.json').write_text(json.dumps({'gen':{'items':[{'issue':'설치','content':'과거 관찰 기록입니다.','sources':['Hacker News'],'refs':['H1'],'primary_url':url}]}}))
            result=module.gather(root,'2026-11-02',2)
            updated=next(row for row in result['evidence']if 'genuinely' in row['text'])
            self.assertFalse(updated['already_published'])
            self.assertTrue(updated['source_previously_cited_by'])
    def test_private_source_excerpt_marks_only_matching_evidence(self):
        with tempfile.TemporaryDirectory()as root:
            used='실제로 음성을 실행한 결과 처리 속도가 느렸다고 설명했다.'
            new='다른 사용자가 연결 설정 방법을 어떻게 하는지 질문했다.'
            self.checkpoint(root,'2026-11-02','===== [오픈채팅 · 모임 3 (비공개 대화)] =====\n'+used+'\n'+new)
            Path(root,'2026-11-02.json').write_text(json.dumps({'gen':{'items':[{'issue':'음성 처리','content':'음성 처리 속도에 관한 사례.','sources':['오픈채팅 · 모임 3'],'refs':[],'_knowledge':{'source_excerpt':used}}]}}))
            result=module.gather(root,'2026-11-02',1)
            self.assertEqual({x['text']:x['already_published']for x in result['evidence']},{used:True,new:False})
    def test_missing_corrupt_pending_and_unsafe_url_are_not_complete(self):
        with tempfile.TemporaryDirectory()as root:
            path=Path(root)/'checkpoints';path.mkdir()
            (path/'2026-11-01.json').write_text('{bad')
            (path/'2026-11-02.json').write_text(json.dumps({'stage':'collecting'}))
            result=module.gather(root,'2026-11-02',3,extra_web=[{'source':'Reddit','text':'A useful public report about a software failure.','url':'https://user:secret@example.org/'}])
            self.assertEqual(result['coverage']['missing_checkpoint_dates'],['2026-10-31','2026-11-02'])
            self.assertEqual(result['coverage']['errors'],[{'date':'2026-11-01','kind':'invalid_checkpoint_snapshot'}])
            self.assertEqual(result['evidence'][0]['url'],'')
            self.assertFalse(result['publication_allowed'])
    def test_window_excludes_old_input_and_current_inputs_share_dedup(self):
        with tempfile.TemporaryDirectory()as root:
            text='A public report describes the actual result of this test.'
            self.checkpoint(root,'2026-10-19','===== [Reddit (글로벌 AI 커뮤니티)] =====\n[R1] '+text,{'R1':{'url':'https://example.org/old'}})
            self.checkpoint(root,'2026-11-02','===== [Reddit (글로벌 AI 커뮤니티)] =====\n[R1] '+text,{'R1':{'url':'https://example.org/new'}},stage='evaluating')
            result=module.gather(root,'2026-11-02',14,extra_web=[{'source':'Reddit','text':text,'url':'https://example.org/new'}])
            self.assertEqual(len(result['evidence']),1)
            self.assertEqual(result['evidence'][0]['observed_dates'],['2026-11-02'])
            self.assertEqual(result['window_start'],'2026-10-20')
            self.assertEqual(result['coverage']['checkpoint_receipts'][0]['stage'],'evaluating')
    def test_noise_and_invalid_window(self):
        with tempfile.TemporaryDirectory()as root:
            result=module.gather(root,'2026-11-02',1,extra_rooms={'오픈채팅 · 모임 2':'네\n사진\nhttps://example.org/\n실제 기능 설정 방법을 공유한 유용한 대화입니다.'})
            self.assertEqual(len(result['evidence']),1)
            for bad in (0,15,True):
                with self.assertRaises(ValueError):module.gather(root,'2026-11-02',bad)

if __name__=='__main__':unittest.main()
