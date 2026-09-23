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

    def test_installs_all_harness_skills_in_two_shared_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.cli(root, 'install-skills', '--project', str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            shared = root / '.agents/skills/super-review'
            claude = root / '.claude/skills/super-review'
            self.assertTrue((shared / 'agents/openai.yaml').is_file())
            self.assertEqual((shared / 'SKILL.md').read_bytes(), (claude / 'SKILL.md').read_bytes())
            self.assertFalse((root / '.cursor').exists())
            self.assertFalse((root / '.opencode').exists())
            (shared / 'user-notes.txt').write_text('keep this')
            repeat = self.cli(root, 'install-skills', '--project', str(root))
            self.assertEqual(repeat.returncode, 0, repeat.stderr)
            self.assertEqual((shared / 'user-notes.txt').read_text(), 'keep this')
            self.assertEqual(list(root.rglob('.super-review-skill-backups')), [])

    def test_selected_harnesses_reuse_their_discovery_directories(self):
        for selection, expected in [('codex', '.agents'), ('cursor', '.agents'),
                                    ('opencode', '.agents'), ('claude_code', '.claude'),
                                    ('codex,cursor,opencode,cursor', '.agents')]:
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = self.cli(root, 'install-skills', '--project', str(root),
                                  '--harnesses', selection)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(list(root.glob('*/skills/super-review/SKILL.md')),
                                 [root / expected / 'skills/super-review/SKILL.md'])

    def test_all_destinations_are_checked_before_installing_or_replacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            customized = root / '.claude/skills/super-review'
            customized.mkdir(parents=True)
            (customized / 'SKILL.md').write_text('custom workflow')
            (customized / 'extra.txt').write_text('custom resource')
            refused = self.cli(root, 'install-skills', '--project', str(root))
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((root / '.agents').exists())
            self.assertEqual((customized / 'SKILL.md').read_text(), 'custom workflow')
            forced = self.cli(root, 'install-skills', '--project', str(root), '--force')
            self.assertEqual(forced.returncode, 0, forced.stderr)
            backups = list((root / '.claude/.super-review-skill-backups').glob('super-review-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'extra.txt').read_text(), 'custom resource')
            self.assertEqual((backups[0] / 'SKILL.md').read_text(), 'custom workflow')

    def test_invalid_harness_selection_and_symlinks_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for selection in ('', 'codex,typo', 'cursor,'):
                result = self.cli(root, 'install-skills', '--project', str(root),
                                  '--harnesses', selection)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list(root.iterdir()), [])
            outside = root / 'other'
            outside.mkdir()
            (outside / 'SKILL.md').write_text('outside skill')
            link = root / '.claude/skills/super-review'
            link.parent.mkdir(parents=True)
            link.symlink_to(outside, target_is_directory=True)
            result = self.cli(root, 'install-skills', '--project', str(root), '--force')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('symlink', result.stderr)
            self.assertFalse((root / '.agents').exists())
            self.assertEqual((outside / 'SKILL.md').read_text(), 'outside skill')

    def test_default_skill_install_uses_home_without_changing_project(self):
        from contextlib import redirect_stdout
        import io
        from super_review.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(Path, 'home', return_value=root), redirect_stdout(io.StringIO()):
                result = main(['install-skills'])
            self.assertEqual(result, 0)
            self.assertTrue((root / '.agents/skills/super-review/SKILL.md').is_file())
            self.assertTrue((root / '.claude/skills/super-review/SKILL.md').is_file())

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
