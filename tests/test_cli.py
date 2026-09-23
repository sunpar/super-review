import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_relative_harness_executable_survives_workspace_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, _ = make_repo(root)
            (repo / 'python-cli').symlink_to(sys.executable)
            fixture = str(Path(__file__).with_name('fake_harness.py').resolve())
            command = ['./python-cli', fixture, 'codex', str(root / 'events.jsonl'), '']
            # An empty wrapper argument is not permitted by configuration.
            command[-1] = 'no-failure'
            (repo / 'super-review.toml').write_text(
                '[run]\nreviewers = ["correctness"]\n'
                '[harnesses.codex]\ncommand = ' + json.dumps(command) + '\n')
            result = self.cli(repo, 'run', '--base', base, '--output', str(root / 'runs'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(Path(result.stdout.strip()).is_file())

    def test_installs_codex_skill_and_backs_up_customized_copy_only_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'skills' / 'super-review'
            result = self.cli(root, 'install-codex-skill', '--path', str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / 'SKILL.md'
            original = skill.read_text()
            self.assertTrue((target / 'agents' / 'openai.yaml').is_file())
            repeat = self.cli(root, 'install-codex-skill', '--path', str(target))
            self.assertEqual(repeat.returncode, 0, repeat.stderr)
            skill.write_text('my customization')
            refused = self.cli(root, 'install-codex-skill', '--path', str(target))
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(skill.read_text(), 'my customization')
            forced = self.cli(root, 'install-codex-skill', '--path', str(target), '--force')
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertEqual(skill.read_text(), original)
            backups = list((root / '.super-review-skill-backups').glob('super-review-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'SKILL.md').read_text(), 'my customization')

    def test_workers_cannot_launch_or_resume_another_swarm(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SUPER_REVIEW_WORKER': '1'}):
            root = Path(tmp)
            for args in [('run', '--base', 'HEAD~1'), ('resume', str(root / 'run'))]:
                result = self.cli(root, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('worker', result.stderr.lower())
                self.assertIn('nested', result.stderr.lower())

    def test_review_message_reaches_all_phases_literally_and_workers_are_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, _ = make_repo(root)
            events = root / 'events.jsonl'
            fixture = str(Path(__file__).with_name('fake_harness.py').resolve())
            commands = {h: [sys.executable, fixture, h, str(events), 'no-failure']
                        for h in ('codex', 'claude_code')}
            (repo / 'super-review.toml').write_text(
                '[run]\nharnesses = ["codex", "claude_code"]\nreviewers = ["correctness"]\n'
                + ''.join(f'[harnesses.{h}]\ncommand = {json.dumps(command)}\n'
                          for h, command in commands.items()))
            message = 'Focus on SQL joins; literal `$(touch NEVER)` and "quotes".\nSecond line.'
            with patch.dict(os.environ, {'SUPER_REVIEW_TEST_EXPECT_INTENT': message}):
                result = self.cli(repo, 'run', '--base', base, '--intent', message,
                                  '--output', str(root / 'runs'))
            self.assertEqual(result.returncode, 0, result.stderr)
            report = Path(result.stdout.strip())
            manifest = json.loads((report.parent / 'manifest.json').read_text())
            self.assertEqual(manifest['requirements'], message)
            records = [json.loads(line) for line in events.read_text().splitlines()]
            self.assertEqual({r['phase'] for r in records},
                             {'specialist', 'coordinator', 'critique', 'revision', 'synthesis'})
            self.assertTrue(all(r['worker'] == '1' for r in records))
            self.assertFalse((repo / 'NEVER').exists())
