"""Exercise publication against real, local Git repositories without network access."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from aidaily.publishing.repository import publish_generated


class IsolatedPublicationTests(unittest.TestCase):
    def git(self, root, *arguments):
        return subprocess.check_output(['git', *arguments], cwd=root, stderr=subprocess.DEVNULL)

    def test_collision_dirty_and_staged_work_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote, runtime, publisher = (root / name for name in ('remote.git', 'runtime', 'publisher'))
            self.git(root, 'init', '--bare', '--initial-branch=main', str(remote))
            self.git(root, 'clone', str(remote), str(runtime))
            self.git(runtime, 'config', 'user.name', 'Test')
            self.git(runtime, 'config', 'user.email', 'test@example.invalid')
            (runtime / 'source.py').write_text('original\n')
            self.git(runtime, 'add', '.')
            self.git(runtime, 'commit', '-m', 'initial')
            self.git(runtime, 'push', 'origin', 'main')
            self.git(root, 'clone', str(remote), str(publisher))
            self.git(publisher, 'config', 'user.name', 'Test')
            self.git(publisher, 'config', 'user.email', 'test@example.invalid')
            (publisher / 'docs').mkdir()
            (publisher / 'docs/today.html').write_text('remote copy')
            (publisher / 'remote-only.txt').write_text('preserve history')
            self.git(publisher, 'add', '.')
            self.git(publisher, 'commit', '-m', 'remote publication')
            self.git(publisher, 'push', 'origin', 'main')
            ancestor = self.git(publisher, 'rev-parse', 'HEAD').strip().decode()
            (runtime / 'docs').mkdir()
            (runtime / 'docs/today.html').write_text('new generated copy')
            (runtime / 'docs/private.txt').write_text('do not publish')
            (runtime / 'source.py').write_text('staged edit\n')
            self.git(runtime, 'add', 'source.py')
            (runtime / 'source.py').write_text('unstaged edit\n')
            status = self.git(runtime, 'status', '--porcelain=v1', '--untracked-files=all')
            staged = self.git(runtime, 'diff', '--cached')
            head = self.git(runtime, 'rev-parse', 'HEAD')
            self.assertTrue(publish_generated(runtime, ['docs/today.html'], 'publish'))
            self.assertEqual(status, self.git(runtime, 'status', '--porcelain=v1', '--untracked-files=all'))
            self.assertEqual(staged, self.git(runtime, 'diff', '--cached'))
            self.assertEqual(head, self.git(runtime, 'rev-parse', 'HEAD'))
            self.assertEqual((runtime / 'source.py').read_text(), 'unstaged edit\n')
            self.assertEqual(self.git(remote, 'show', 'main:docs/today.html'), b'new generated copy')
            self.assertEqual(self.git(remote, 'show', 'main:source.py'), b'original\n')
            self.assertEqual(self.git(remote, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main'), b'docs/today.html\n')
            self.git(remote, 'merge-base', '--is-ancestor', ancestor, 'main')
            self.assertFalse(publish_generated(runtime, ['docs/today.html'], 'unchanged'))
            before = self.git(remote, 'rev-parse', 'main')
            (runtime / 'docs/today.html').write_text('dry run output')
            self.assertTrue(publish_generated(runtime, ['docs/today.html'], 'dry-run', dry_run=True))
            self.assertEqual(before, self.git(remote, 'rev-parse', 'main'))
            self.assertEqual(head, self.git(runtime, 'rev-parse', 'HEAD'))
            self.assertEqual(staged, self.git(runtime, 'diff', '--cached'))
            for path in ['../escape', '.', '.git/config']:
                with self.assertRaises(ValueError):
                    publish_generated(runtime, [path], 'invalid')


if __name__ == '__main__':
    unittest.main()
