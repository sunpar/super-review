from pathlib import Path
import shutil
import tempfile
import unittest

from support import make_repo, git
from super_review.git import resolve_target, create_snapshot, workspace, assert_clean


class GitTests(unittest.TestCase):
    def test_snapshot_does_not_borrow_objects_from_shared_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, base, head = make_repo(root)
            borrowed = root / 'borrowed'
            git(root, 'clone', '--shared', str(upstream), str(borrowed))
            target = resolve_target(borrowed, base, head)
            snap = root / 'snapshot.git'
            create_snapshot(borrowed, snap, target)
            shutil.rmtree(upstream)
            with workspace(snap, root / 'task', head) as cwd:
                self.assertIn('return a - b', (cwd / 'calc.py').read_text())

    def test_all_submodule_change_kinds_are_rejected(self):
        for change in ('add', 'modify', 'delete', 'replace'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                repo, first, second = make_repo(Path(tmp))
                if change != 'add':
                    git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{first},sub')
                    git(repo, 'commit', '-m', 'gitlink base')
                base = git(repo, 'rev-parse', 'HEAD')
                if change in ('delete', 'replace'):
                    git(repo, 'update-index', '--force-remove', 'sub')
                    if change == 'replace':
                        (repo / 'sub').write_text('now a regular file')
                        git(repo, 'add', 'sub')
                else:
                    git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{second},sub')
                git(repo, 'commit', '-m', change)
                with self.assertRaisesRegex(ValueError, 'submodules'):
                    resolve_target(repo, base, 'HEAD')

    def test_pinned_snapshot_survives_source_branch_moving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = make_repo(root)
            target = resolve_target(repo, base, 'HEAD')
            snap = root / 'snapshot.git'
            create_snapshot(repo, snap, target)
            (repo / 'calc.py').write_text('new uncommitted content')
            with workspace(snap, root / 'task', head) as cwd:
                self.assertEqual((cwd / 'calc.py').read_text(), 'def total(a, b):\n    return a - b\n')
                self.assertEqual(git(cwd, 'remote'), '')
                assert_clean(cwd, head)
                (cwd / 'calc.py').write_text('modified')
                with self.assertRaisesRegex(ValueError, 'modified'):
                    assert_clean(cwd, head)
            self.assertFalse((root / 'task').exists())
            self.assertEqual((repo / 'calc.py').read_text(), 'new uncommitted content')

    def test_reject_option_like_refs_and_empty_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, head = make_repo(Path(tmp))
            with self.assertRaises(ValueError):
                resolve_target(repo, '--help', 'HEAD')
            with self.assertRaisesRegex(ValueError, 'No committed changes'):
                resolve_target(repo, head, head)
