"""Formatting regressions: policy prose becomes bullets without content edits."""
import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('policy_prd_format_under_test', Path(__file__).resolve().parents[1] / 'deploy/policy_prd_format.py')
formatter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatter)


def content(markdown):
    return re.sub(r'\s+', ' ', re.sub(r'(?m)^- ', '', markdown)).strip()


class PolicyPrdFormatTests(unittest.TestCase):
    def test_sentences_become_individual_bullets_without_wording_change(self):
        source = '게시 후 확인한다. 실패하면 재전송하지 않는다! 예외는 승인 범위만 따른다?\n'
        expected = '- 게시 후 확인한다.\n- 실패하면 재전송하지 않는다!\n- 예외는 승인 범위만 따른다?\n'
        self.assertEqual(formatter.bullet_prose(source), expected)
        self.assertEqual(content(source), content(expected))

    def test_inline_commands_links_versions_and_decimals_are_preserved(self):
        source = '명령 `python3 tool.py --text "첫 문장. 다음 문장"`을 쓴다. 버전 1.0.1과 값 0.3은 유지한다. [문서. 참고](https://example.com/a.b?text=one. two)를 따른다.\n'
        result = formatter.bullet_prose(source)
        self.assertEqual(result.count('\n- '), 2)
        self.assertIn('`python3 tool.py --text "첫 문장. 다음 문장"`', result)
        self.assertIn('[문서. 참고](https://example.com/a.b?text=one. two)', result)
        self.assertIn('1.0.1과 값 0.3', result)
        self.assertEqual(content(source), content(result))

    def test_structural_blocks_are_byte_preserved(self):
        source = '# 제목\n\n## 소제목\n| 조건 | 내용 |\n|---|---|\n| 하나 | 문장. 예외. |\n\n- 기존 항목. 다음 문장.\n  - 하위 항목. 예외.\n* 별표 항목. 그대로.\n1. 번호 목록. 그대로.\n> 인용. 그대로.\n---\n    들여쓴 코드. 그대로.\n\t탭 코드. 그대로.\n'
        self.assertEqual(formatter.bullet_prose(source), source)

    def test_fenced_code_and_embedded_shorter_fences_are_preserved(self):
        source = '````python\ntext = "문장. 예외."\n```\n코드 안의 문장. 계속 코드.\n````\n~~~json\n{"text":"문장. 유지."}\n~~~\n본문이다. 예외도 남긴다.\n'
        result = formatter.bullet_prose(source)
        self.assertEqual(result.split('본문이다.')[0], source.split('본문이다.')[0] + '- ')
        self.assertTrue(result.endswith('- 본문이다.\n- 예외도 남긴다.\n'))
        self.assertEqual(content(source), content(result))

    def test_idempotent_and_trailing_newline_preserved(self):
        for source in ('문장. 다음 문장.', '문장. 다음 문장.\n', '', '# 제목\n- 목록\n'):
            with self.subTest(source=source):
                result = formatter.bullet_prose(source)
                self.assertEqual(formatter.bullet_prose(result), result)
                self.assertEqual(result.endswith('\n'), source.endswith('\n'))
                self.assertEqual(content(source), content(result))

    def test_quoted_inline_double_backtick_command_remains_one_sentence(self):
        source = '명령 ``echo `date`; print("one. two")``는 보존한다. 다음 정책이다.'
        result = formatter.bullet_prose(source)
        self.assertEqual(result.count('\n- '), 1)
        self.assertEqual(content(source), content(result))


if __name__ == '__main__':
    unittest.main()
