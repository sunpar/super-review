import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import make_repo


class CliTests(unittest.TestCase):
    def cli(self, cwd, *args):
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1] / 'src')}
        return subprocess.run([sys.executable, '-m', 'super_review', *args], cwd=cwd,
                              capture_output=True, text=True, env=env)

    def test_init_wont_overwrite_and_default_template_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.cli(root, 'init')
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self.cli(root, 'init')
            self.assertNotEqual(second.returncode, 0)
            from super_review.config import load_config
            self.assertEqual(load_config(root / 'super-review.toml')['run']['harnesses'], ['codex'])

    def test_dry_run_needs_no_installed_harness_and_creates_no_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = make_repo(root)
            result = self.cli(repo, 'run', '--base', base, '--dry-run', '--harnesses',
                              'codex,claude_code,cursor,opencode', '--output', str(root / 'runs'))
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan['total_jobs'], 61)
            self.assertEqual(plan['target']['head_sha'], head)
            self.assertFalse((root / 'runs').exists())

    def test_invalid_config_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.toml').write_text('[run]\nconcurrency = 0\n')
            result = self.cli(root, 'doctor', '--config', 'bad.toml')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('concurrency', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
