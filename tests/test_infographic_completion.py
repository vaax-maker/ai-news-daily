import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path.home() / 'nlm-infographic/deploy/gen_infographics.py'


class InfographicCompletionTests(unittest.TestCase):
    def invoke(self, root):
        # Replace extraction before executing the real CLI, so a failed item
        # never invokes the browser or any image provider.
        code = '''
import runpy, sys
sys.path.insert(0, sys.argv[1])
import ig_backfill_daily
def fail_extract(path):
    raise ValueError("fixture extraction failure")
ig_backfill_daily.extract = fail_extract
script, root = sys.argv[2:]
sys.argv = [script, "2026-11-03", "--webroot", root]
runpy.run_path(script, run_name="__main__")
'''
        return subprocess.run([sys.executable, '-c', code, str(SCRIPT.parent),
                               str(SCRIPT), str(root)], capture_output=True, text=True,
                              timeout=10)

    def test_cli_no_failures_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke(directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_failed_item_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '2026-11-03-fixture.html').write_text(
                'YOUTUBE SUMMARIES · 2026-11-03', encoding='utf-8')
            result = self.invoke(directory)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('fixture extraction failure', result.stdout)

    def test_cli_fatal_error_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke(Path(directory) / 'missing')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('치명 오류', result.stdout)


if __name__ == '__main__':
    unittest.main()
