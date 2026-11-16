import os
import tempfile
import unittest
from unittest.mock import patch
from aidaily.youtube_summaries.evidence_quality import issues
from aidaily.integrations import openrouter


class GroundedQuality(unittest.TestCase):
    def test_cited_facts_pass_and_invented_number_or_name_fails(self):
        quotes=[{'id':'S001-1','quote':'강영화 디자이너는 2023년에 서비스를 시작했습니다.'}]
        report={'headline':'강영화 디자이너가 2023년에 서비스를 시작했다.','card_summary':'서비스 시작',
            '_evidence':{'headline':['S001-1'],'card_summary':['S001-1']}}
        self.assertEqual(issues(report,quotes),[])
        report['headline']='강영아 디자이너가 2026년에 서비스를 시작했다.'
        self.assertIn('headline:unsupported_number',issues(report,quotes))
        self.assertIn('headline:unsupported_name',issues(report,quotes))

    def test_unknown_source_id_and_contact_disclosure_are_review_conditions(self):
        out={'headline':'010-1234-5678로 연락하세요.','card_summary':'소개',
            '_evidence':{'headline':['S001-1'],'card_summary':['invented']}}
        failed=issues(out,[{'id':'S001-1','quote':'연락처 010-1234-5678'}])
        self.assertIn('headline:contact_disclosure',failed)
        self.assertIn('card_summary:missing_source',failed)

    def test_local_quality_operation_cannot_submit_external_on_unavailability(self):
        class Client:
            def chat(self,*a,**kw):return kw['fallback'](None,{'reason':'local_not_ready'})
        with tempfile.TemporaryDirectory() as state,patch.dict(os.environ,{'AIDAILY_LLM_STATE_DIR':state}),patch.object(openrouter,'_new_client',return_value=Client()),patch.object(openrouter,'_load_key') as key:
            with self.assertRaises(openrouter.RoutingBlocked):
                openrouter.complete('근거 검증','원문',request_id='local-quality-no-paid',allow_external=False)
            key.assert_not_called()


class KoreanCounterAndRoleTests(unittest.TestCase):
    def test_korean_counter_is_numeric_evidence_but_generic_role_is_not_a_name(self):
        q=[{'id':'S001-1','quote':'여섯 개 아웃풋을 비교했다. 데이터 성장에 기여하는 디자이너라고 말했다.'}]
        r={'headline':'6개 아웃풋 비교','card_summary':'기여하는 디자이너의 비교', '_evidence':{'headline':['S001-1'],'card_summary':['S001-1']}}
        self.assertEqual(issues(r,q),[])
        r['headline']='7개 아웃풋 비교'
        self.assertIn('headline:unsupported_number',issues(r,q))

    def test_semantic_review_requires_complete_coverage_and_rejects_start_launch_swap(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        q=[{'id':'S001-1','quote':'2023년에 시작했다.'}]
        r={'headline':'2023년에 출시했다.','card_summary':'서비스 소개','_evidence':{'headline':['S001-1'],'card_summary':['S001-1']}}
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline'],'unsupported':[]}):
            self.assertEqual(semantic_issues(r,q),[])
            self.assertTrue(any(w['reason']=='incomplete' for w in r['_quality_warnings']))
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline','card_summary'],'unsupported':[{'path':'headline','reason':'출시일은 확인되지 않음'}]}) as call:
            self.assertEqual(semantic_issues(r,q),[])
            self.assertTrue(any(w.get('legacy') for w in r['_quality_warnings']))
        self.assertFalse(call.call_args.kwargs['allow_external'])


class NarrowCorrectionTests(unittest.TestCase):
    def test_only_rejected_field_changes_original_and_good_claims_preserved(self):
        from aidaily.youtube_summaries.evidence_quality import repair_fields
        source=[{'id':'S001-1','quote':'2023년에 시작했다고 말했다.'}]
        out={'headline':'2023년에 출시했다.','card_summary':'화자의 경험 소개','_evidence':{'headline':['S001-1'],'card_summary':['S001-1']}}
        response={'updates':{'headline':{'text':'화자는 2023년에 시작했다고 말했다.','ids':['S001-1']}}}
        with patch.object(openrouter,'complete_json',return_value=response) as call:
            fixed=repair_fields(out,source,['headline:출시일은 원문에 없음'])
            self.assertEqual(fixed['card_summary'],out['card_summary']);self.assertNotEqual(fixed['headline'],out['headline']);self.assertEqual(out['headline'],'2023년에 출시했다.')
        self.assertFalse(call.call_args.kwargs['allow_external'])
        with patch.object(openrouter,'complete_json',return_value={'updates':{'slug_hint':{'text':'override','ids':['S001-1']}}}):
            with self.assertRaises(RuntimeError):repair_fields(out,source,['headline:unproven'])


class CitationBindingTests(unittest.TestCase):
    def test_claim_cannot_borrow_technical_term_from_an_uncited_quote(self):
        quotes=[{'id':'S001-1','quote':'LM은 결정적이지 않은 것을 내보낸다.'},{'id':'S001-2','quote':'구체적인 시나리오를 입력했다.'},{'id':'S001-3','quote':'기존 앱과 다른 언어를 사용했다.'}]
        out={'headline':'구체적인 시나리오를 입력했다.','card_summary':'다른 언어를 사용했다.','_evidence':{'headline':['S001-1'],'card_summary':['S001-1']}}
        bad=issues(out,quotes)
        self.assertTrue(any(p.startswith('headline:uncited_source_term:') for p in bad));self.assertTrue(any(p.startswith('card_summary:uncited_source_term:') for p in bad))
        out['_evidence']={'headline':['S001-2'],'card_summary':['S001-3']}
        self.assertEqual(issues(out,quotes),[])

class LiteralFinalCorrectionTests(unittest.TestCase):
    def test_failed_claim_becomes_literal_cited_source(self):
        from aidaily.youtube_summaries.evidence_quality import literal_repair_fields, diagnose
        q=[{'id':'S1','quote':'2023년에 서비스를 시작했다고 말했다.'}]
        out={'headline':'2026년에 서비스를 출시했다.','card_summary':'서비스 소개','_evidence':{'headline':['S1'],'card_summary':['S1']}}
        fixed=literal_repair_fields(out,q,diagnose(out,q)['issues'])
        self.assertEqual(fixed['headline'],'화자의 발언: “2023년에 서비스를 시작했다고 말했다.”')
        self.assertEqual(fixed['card_summary'],out['card_summary']);self.assertEqual(issues(fixed,q),[])
        self.assertIn('2026',out['headline'])
    def test_unsafe_missing_unrelated_or_english_quote_stays_blocked(self):
        from aidaily.youtube_summaries.evidence_quality import literal_repair_fields
        for quote,ids in [('연락처는 010-1234-5678로 보내주세요.',['S1']),('서로 전혀 관계없는 여러 가지 발언입니다.',['S1']),('서비스를 시작했다고 이야기했습니다.',[]),('The service started in 2023 and supports local models.',['S1'])]:
            with self.subTest(quote=quote):
                out={'headline':'서비스를 2026년에 시작했다.','card_summary':'소개','_evidence':{'headline':ids,'card_summary':['S1']}}
                with self.assertRaises(RuntimeError):literal_repair_fields(out,[{'id':'S1','quote':quote}],['headline:unsupported_number'])
    def test_glossary_unrelated_quote_stays_blocked(self):
        from aidaily.youtube_summaries.evidence_quality import literal_repair_fields
        out={'headline':'소개','card_summary':'소개','glossary':[{'term':'추론','definition':'모델 학습의 비용'}],'_evidence':{'glossary.0.definition':['S1']}}
        with self.assertRaises(RuntimeError):literal_repair_fields(out,[{'id':'S1','quote':'모델 학습의 비용을 비교해서 설명했습니다.'}],['glossary.0.definition:unsupported'])

class ExactQuantityNormalizationTests(unittest.TestCase):
    def test_decimal_korean_multipliers_are_exact_equivalents(self):
        from aidaily.youtube_summaries.evidence_quality import numbers
        self.assertEqual(numbers('10만 개'),numbers('100,000개'))
        self.assertEqual(numbers('1.5억 원'),numbers('150,000,000원'))
        self.assertNotEqual(numbers('100개 이상'),numbers('100,000개'))

class PrivateDiagnosticTests(unittest.TestCase):
    def test_failure_diagnostics_preserve_exact_report_in_private_file(self):
        import json
        from pathlib import Path
        from aidaily import config
        from aidaily.youtube_summaries.analyzer import _quality_failure
        with tempfile.TemporaryDirectory() as root,patch.object(config,'DATA_ROOT',Path(root)):
            report={'headline':'원본'};quotes=[{'id':'S1','quote':'원문'}];history=[{'issues':['headline:unsupported_number']}]
            error=_quality_failure(RuntimeError('검수 실패'),history,report,quotes)
            target=Path(error.quality_diagnostics_path)
            self.assertEqual(json.loads(target.read_text()),{'report':report,'quotes':quotes,'history':history})
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertIn(str(target),str(error))

class OptionalPruningTests(unittest.TestCase):
    def report(self):
        return {'headline':'required','card_summary':'required','overview':[f'o{i}' for i in range(5)],'sections':[{'title':'section','bullets':[f'b{i}' for i in range(4)]}],'glossary':[{'term':f't{i}','definition':f'd{i}'} for i in range(4)],'_evidence':{'headline':['H'],'card_summary':['C'],**{f'overview.{i}':[f'O{i}'] for i in range(5)},**{f'sections.0.bullets.{i}':[f'B{i}'] for i in range(4)},**{f'glossary.{i}.definition':[f'G{i}'] for i in range(4)}}}
    def test_only_rejected_optional_fields_drop_and_indices_remap(self):
        from aidaily.youtube_summaries.evidence_quality import prune_failed_fields
        original=self.report()
        fixed=prune_failed_fields(original,['overview.1:unsupported','sections.0.bullets.0:unsupported','glossary.2.definition:unsupported'])
        self.assertEqual(len(original['overview']),5);self.assertEqual(fixed['overview'],['o0','o2','o3','o4'])
        self.assertEqual(fixed['_evidence']['overview.1'],['O2'])
        self.assertEqual(fixed['_evidence']['sections.0.bullets.0'],['B1'])
        self.assertEqual(fixed['_evidence']['glossary.2.definition'],['G3'])
        self.assertNotIn('overview.4',fixed['_evidence']);self.assertEqual(fixed['headline'],'required')
    def test_required_minimum_or_review_protocol_cannot_be_pruned(self):
        from aidaily.youtube_summaries.evidence_quality import prune_failed_fields
        for bad in [['headline:unsupported'],['card_summary:unsupported'],['semantic_review:incomplete'],['overview.0:x','overview.1:x'],['glossary.0.definition:x','glossary.1.definition:x']]:
            with self.subTest(bad=bad),self.assertRaises(RuntimeError):prune_failed_fields(self.report(),bad)
    def test_final_english_optional_field_is_omitted_not_padded(self):
        from aidaily.youtube_summaries.evidence_quality import final_repair_fields
        out=self.report();out['_evidence']['glossary.2.definition']=['S1']
        fixed=final_repair_fields(out,[{'id':'S1','quote':'This unsupported source remains an English quotation.'}],['glossary.2.definition:unsupported'])
        self.assertEqual(len(fixed['glossary']),3)
        self.assertEqual([r['term'] for r in fixed['glossary']],['t0','t1','t3'])

class StableSemanticGroupTests(unittest.TestCase):
    def report(self):
        from aidaily.youtube_summaries.evidence_quality import fields
        out={'headline':'서비스 원문','card_summary':'서비스 원문','overview':['서비스 원문']*5,'sections':[{'title':'내용','bullets':['서비스 원문']*4} for _ in range(3)],'glossary':[{'term':'서비스','definition':'서비스 원문'} for _ in range(4)]}
        out['_evidence']={p:['S1'] for p,t in fields(out)}
        return out
    def reviewer(self,system,user,**kw):
        import json
        return {'checked':[c['path'] for c in json.loads(user)['claims']],'unsupported':[]}
    def test_pruning_retains_other_groups_identical_inputs(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues,prune_failed_fields
        out=self.report();q=[{'id':'S1','quote':'서비스 원문 근거를 설명했습니다.'}]
        with patch.object(openrouter,'complete_json',side_effect=self.reviewer) as first:
            self.assertEqual(semantic_issues(out,q),[])
        old=[c.args[1] for c in first.call_args_list]
        fixed=prune_failed_fields(out,['overview.0:unsupported'])
        with patch.object(openrouter,'complete_json',side_effect=self.reviewer) as second:
            self.assertEqual(semantic_issues(fixed,q),[])
        new=[c.args[1] for c in second.call_args_list]
        self.assertEqual(len(old),len(new))
        self.assertEqual(old[2:],new[2:])
        self.assertEqual(len(fixed['_semantic_review_groups'][0]),5)
        self.assertNotEqual(old[0],new[0])
    def test_duplicate_or_missing_plan_fails_closed(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        q=[{'id':'S1','quote':'서비스 원문 근거'}]
        for plan in [[['headline','headline']],[['headline']]]:
            out=self.report();out['_semantic_review_groups']=plan
            with patch.object(openrouter,'complete_json') as call:
                self.assertEqual(semantic_issues(out,q),[])
                self.assertTrue(any(w['reason']=='incomplete_group_plan' for w in out['_quality_warnings']))
                call.assert_not_called()
    def test_modified_text_is_still_reviewed_in_existing_group(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        out=self.report();q=[{'id':'S1','quote':'서비스 원문 근거'}]
        with patch.object(openrouter,'complete_json',side_effect=self.reviewer):semantic_issues(out,q)
        out['sections'][2]['bullets'][1]='새로운 미지원 주장'
        with patch.object(openrouter,'complete_json',side_effect=self.reviewer) as call:semantic_issues(out,q)
        self.assertTrue(any('새로운 미지원 주장' in c.args[1] for c in call.call_args_list))

class CriticalFactsPolicyTests(unittest.TestCase):
    def report(self):
        return {'headline':'7명이 참여했다.','card_summary':'참여자 소개','_evidence':{'headline':['S1'],'card_summary':['S1']}}
    def quotes(self):return [{'id':'S1','quote':'원문에는 3명이 참여했다고 명시했다.'}]
    def critical(self):
        return {'path':'headline','reason':'참여자 3명을 7명으로 바꾼 핵심 수치 모순','severity':'critical','kind':'contradiction','evidence':{'claim':'7명이 참여','source_id':'S1','source_quote':'3명이 참여'}}
    def test_equivalent_ordinal_range_spacing_and_korean_multiplier(self):
        from aidaily.youtube_summaries.evidence_quality import numbers
        for left,right in [('first','1'),('a day or two','1~2일'),('39 000','39000'),('여섯 배','6배')]:
            self.assertEqual(numbers(left),numbers(right),(left,right))
    def test_lexical_number_and_name_mismatches_are_advisory_not_structural_blocks(self):
        from aidaily.youtube_summaries.evidence_quality import blocking_issues,diagnose
        r=self.report();self.assertIn('headline:unsupported_number',issues(r,self.quotes()))
        self.assertEqual(blocking_issues(r,self.quotes()),[])
        self.assertIn('headline:unsupported_number',diagnose(r,self.quotes())['advisory_issues'])
        r['_evidence']['headline']=['missing'];self.assertIn('headline:missing_source',blocking_issues(r,self.quotes()))
        r=self.report();r['headline']='연락처 x@example.com';self.assertIn('headline:contact_disclosure',blocking_issues(r,self.quotes()))
    def test_only_critical_kind_and_literal_cited_proof_blocks(self):
        import copy
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        entry=self.critical()
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline','card_summary'],'unsupported':[entry]}):
            self.assertEqual(len(semantic_issues(self.report(),self.quotes())),1)
        for change in ({'severity':'advisory'},{'kind':'expression'},{'evidence':{}},{'evidence':{'claim':'7명이 참여','source_id':'S1','source_quote':'없는 원문'}}):
            altered=copy.deepcopy(entry);altered.update(change);r=self.report()
            with patch.object(openrouter,'complete_json',return_value={'checked':['headline','card_summary'],'unsupported':[altered]}):self.assertEqual(semantic_issues(r,self.quotes()),[])
            self.assertTrue(r['_quality_warnings'])
    def test_short_literal_numeric_proof_still_blocks_critical_contradiction(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        r=self.report();r['headline']='50명 참여';q=[{'id':'S1','quote':'5명 참여'}]
        row=self.critical();row['evidence']={'claim':'50명','source_id':'S1','source_quote':'5명'}
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline','card_summary'],'unsupported':[row]}):
            self.assertEqual(len(semantic_issues(r,q)),1)
    def test_legacy_and_incomplete_responses_warn_and_warning_reset_deduplicates(self):
        from aidaily.youtube_summaries.evidence_quality import semantic_issues
        legacy={'path':'headline','reason':'표현 다름'};r=self.report()
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline'],'unsupported':[legacy,legacy]}):
            self.assertEqual(semantic_issues(r,self.quotes()),[])
        self.assertEqual(len(r['_quality_warnings']),2)
        with patch.object(openrouter,'complete_json',return_value={'checked':['headline','card_summary'],'unsupported':[]}):semantic_issues(r,self.quotes())
        self.assertEqual(r['_quality_warnings'],[])
    def test_pending_and_auth_contract_exceptions_propagate(self):
        from aidaily.youtube_summaries import evidence_quality,resilient_llm
        for error in (openrouter.CompletionPending('existing-id'),openrouter.RoutingBlocked('authentication')):
            with patch.object(resilient_llm,'complete_json',side_effect=error):
                with self.assertRaises(type(error)):evidence_quality.semantic_issues(self.report(),self.quotes())
    def test_analyzer_disables_all_evidence_checks_for_short_and_long_inputs(self):
        import copy
        from contextlib import ExitStack
        from aidaily.youtube_summaries import analyzer,evidence_quality,source_chunks,resilient_llm
        q=[{'id':'S1','start':0,'end':25,'quote':'서비스를 2023년에 시작했다고 이야기했습니다.'}]
        report={'category':'tech','headline':'서비스를 2026년에 시작했다.','card_summary':'서비스 소개','sections':[{'title':f'서비스 소개 주제 {i}','bullets':['서비스의 시작 시점과 실제 사용 과정을 설명하면서 해당 사례에서 관찰한 변화와 배경을 구체적으로 함께 소개합니다.','서비스를 이용하는 과정에서 확인된 조건을 정리하고 이후의 활용 방식과 제한을 이해할 수 있도록 설명합니다.']}for i in range(6)],'glossary':[{'term':'서비스','definition':'서비스 소개 문장'}for _ in range(3)]}
        for transcript in ('원문 '*100,'원문 '*6000):
            with self.subTest(length=len(transcript)),ExitStack() as stack:
                extract=stack.enter_context(patch.object(source_chunks,'extract',return_value=(q,{})))
                stack.enter_context(patch.object(source_chunks,'bounded_notes',return_value=q))
                generate=stack.enter_context(patch.object(resilient_llm,'complete_json',return_value=copy.deepcopy(report)))
                checks=[stack.enter_context(patch.object(evidence_quality,name,side_effect=AssertionError('disabled evidence function called'))) for name in ('issues','blocking_issues','semantic_issues','repair_fields','final_repair_fields','diagnose','_warnings')]
                result=analyzer.analyze(transcript)
                from aidaily.youtube_summaries.pipeline import build_markdown
                if len(transcript)<15000:
                    self.assertNotIn('## 핵심 개요',build_markdown(result,'제목'))
                    self.assertNotIn('source_analysis',result)
                generate.assert_called_once()
                for check in checks:check.assert_not_called()
                self.assertNotIn('_evidence',result)
                analysis=result.get('source_analysis') or result['summary_validation']
                self.assertEqual(analysis['evidence_quality_gate'],'disabled_by_user')
                self.assertEqual(analysis['quality_checks'],['report_structure'])
                self.assertEqual(analysis['quality_policy']['semantic_calls'],0)
                self.assertNotIn('_evidence',generate.call_args.args[0])
                if len(transcript)>15000:self.assertEqual(analysis['selected_quotes'],q)
                else:extract.assert_not_called()
    def test_analyzer_removes_cached_validation_metadata_and_keeps_structure_gate(self):
        from aidaily.youtube_summaries import analyzer,resilient_llm
        report={'category':'tech','headline':'요약','overview':['개요']*4,'sections':[{'title':f'서비스별 상세 내용 {i}','bullets':['서비스의 실제 사용 과정을 설명하고 해당 사례에서 관찰한 변화와 조건을 구체적으로 이해할 수 있도록 소개합니다.','이 서비스가 사용되는 환경과 이후의 활용 방식을 정리하면서 그 과정에서 언급된 제한도 함께 살펴봅니다.']}for i in range(6)],'glossary':[{'term':'용어','definition':'설명'}for _ in range(3)],'_evidence':{},'_semantic_review_groups':[],'_quality_warnings':['old'],'source_analysis':{'evidence_quality_gate':'passed','quality_review_history':['old']},'quality_warnings':['old']}
        with patch.object(resilient_llm,'complete_json',return_value=report):result=analyzer.analyze('원문 '*100)
        for key in ('_evidence','_semantic_review_groups','_quality_warnings','quality_warnings'):self.assertNotIn(key,result)
        self.assertNotIn('source_analysis',result)
        self.assertNotIn('quality_review_history',result['summary_validation'])
        with patch.object(resilient_llm,'complete_json',return_value={'overview':[]}):
            with self.assertRaises(RuntimeError):analyzer.analyze('원문 '*100)
