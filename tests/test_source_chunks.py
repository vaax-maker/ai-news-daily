import unittest
from unittest.mock import patch
from aidaily.youtube_summaries import source_chunks


class FullSourceTests(unittest.TestCase):
    def test_every_character_covered_with_bounded_balanced_windows(self):
        for size in [6001,16001,38959,50000]:
            text=('가나다라\n'*10000)[:size]
            chunks=list(source_chunks.windows(text))
            self.assertEqual(''.join(c[2] for c in chunks),text)
            self.assertTrue(all(3000<=len(c[2])<=6000 for c in chunks))
            self.assertEqual(chunks[0][0],0);self.assertEqual(chunks[-1][1],len(text))

    def test_whitespace_equivalence_retains_original_quote_and_anchor(self):
        text='원문에서 구간을 확인합니다. '+('사실 근거와 수치를  정확하게 보존하는 설명입니다. '*3)
        quote=text[15:130].replace('  ',' ')
        result=source_chunks.locate_quote(text,quote)
        self.assertIsNotNone(result);self.assertEqual(text[result[0]:result[0]+len(result[1])],result[1])
        self.assertIsNone(source_chunks.locate_quote(text,'근거 없이 만든 수치가 999배 개선됐다는 주장입니다. '*2))

    def test_invalid_model_quotes_stop_without_replacing_source(self):
        text='참고 원문입니다. '*500
        with patch.object(source_chunks.openrouter,'complete_json',return_value={'quotes':[{'quote':'창작된 이야기입니다. '*5,'topic':'창작'}]*4}) as calls:
            with self.assertRaises(RuntimeError):source_chunks.extract(text)
            self.assertEqual(calls.call_count,2)
            self.assertEqual(text,'참고 원문입니다. '*500)

    def test_forged_evidence_selection_rejected(self):
        quotes=[{'id':str(i),'quote':'x'*180,'topic':'t','start':i,'end':i+180} for i in range(70)]
        with patch.object(source_chunks.openrouter,'complete_json',return_value={'ids':['invented']}):
            with self.assertRaises(RuntimeError):source_chunks.bounded_notes(quotes)

    def test_overselection_repaired_once_with_explicit_limit_and_new_identity(self):
        import json
        quotes=[{'id':str(i),'quote':'x'*180,'topic':'t','start':i,'end':i+180} for i in range(70)]
        seen=[]
        def select(system,user,**kwargs):
            batch=json.loads(user);cap=max(1,len(batch)//2)
            seen.append((system,kwargs['request_id'],kwargs.get('allow_external')))
            if len(seen)==1:return {'ids':[q['id'] for q in batch[:cap+1]]}
            return {'ids':[q['id'] for q in batch[:cap]]}
        with patch.object(source_chunks.resilient_llm,'complete_json',side_effect=select):
            selected=source_chunks.bounded_notes(quotes)
        self.assertTrue(selected)
        self.assertIn('-repair-1',seen[1][1])
        self.assertTrue(seen[0][1].startswith('yt-evidence-select-v2-'))
        self.assertIs(seen[1][2],False)
        self.assertIn('반드시 1~',seen[0][0])
        self.assertTrue(all(q in quotes for q in selected))

    def test_invalid_selection_is_bounded_and_preserves_source(self):
        import copy
        quotes=[{'id':str(i),'quote':'x'*180,'topic':'t','start':i,'end':i+180} for i in range(70)]
        original=copy.deepcopy(quotes)
        with patch.object(source_chunks.resilient_llm,'complete_json',return_value={'ids':[{}]}) as call:
            with self.assertRaises(RuntimeError):source_chunks.bounded_notes(quotes)
        self.assertEqual(call.call_count,2)
        self.assertEqual(quotes,original)
