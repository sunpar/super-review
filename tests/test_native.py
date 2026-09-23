import json
from pathlib import Path
import tempfile
import tomllib
import unittest

from super_review.adapters import build_command
from super_review.config import default_config, validate_config
from super_review.native import agent_definitions, codex_role, native_workspace


class NativeAgentTests(unittest.TestCase):
    def test_codex_toml_roundtrips_unicode_prompts_and_paths(self):
        cfg = default_config()
        cfg['reviewer_prompts']['security'] = 'Watch for 🚀 regressions'
        specs = agent_definitions(cfg, 'codex')
        parsed = tomllib.loads(codex_role('super-review-security', specs['super-review-security']))
        self.assertIn('🚀', parsed['developer_instructions'])
        argv, _, _ = build_command('codex', {'command': ['codex']}, Path('/tmp/p'),
                                  specs, Path('/tmp/🚀/native'))
        overrides = [argv[i + 1] for i, arg in enumerate(argv) if arg == '-c']
        for override in overrides:
            parsed = tomllib.loads(override)
            if 'config_file' in override:
                role = next(iter(parsed['agents'].values()))
                self.assertIn('/🚀/', role['config_file'])

    def config(self):
        cfg = default_config()
        cfg['run']['reviewers'] = ['correctness', 'security']
        for h in cfg['harnesses']:
            cfg['harnesses'][h]['defaults'] = {'model': 'base-model'}
            cfg['harnesses'][h]['reviewers']['security'] = {
                'model': 'security-model', 'effort': 'high',
                'effort_models': {'high': 'security-high'}}
        return cfg

    def test_codex_role_files_keep_overrides_and_enable_native_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd, logs = root / 'repo', root / 'logs'
            cwd.mkdir()
            specs = agent_definitions(self.config(), 'codex')
            with native_workspace('codex', specs, cwd, logs, 'parent prompt', 'shared diff') as native_dir:
                role = tomllib.loads((native_dir / 'super-review-security.toml').read_text())
                self.assertEqual(role['model'], 'security-model')
                self.assertEqual(role['model_reasoning_effort'], 'high')
                argv, _, _ = build_command('codex', {'command': ['codex']},
                                            cwd / '.super-review-prompt.md', specs, native_dir)
                self.assertIn('agents.enabled=true', argv)
                key = 'agents.super-review-security.config_file='
                role_path = next(arg.removeprefix(key) for arg in argv if arg.startswith(key))
                self.assertEqual(Path(json.loads(role_path)), native_dir / 'super-review-security.toml')
                self.assertIn('read-only', argv)
                self.assertEqual((cwd / '.super-review-context.md').read_text(), 'shared diff')
            self.assertEqual(list(cwd.iterdir()), [])
            self.assertTrue((logs / 'native-agents.json').is_file())

    def test_claude_parent_can_delegate_only_to_registered_read_only_children(self):
        specs = agent_definitions(self.config(), 'claude_code')
        argv, _, _ = build_command('claude_code', {'command': ['claude']}, Path('/tmp/p'), specs)
        definitions = json.loads(argv[argv.index('--agents') + 1])
        self.assertEqual(set(definitions), {'super-review', 'super-review-correctness', 'super-review-security'})
        self.assertIn('Agent(super-review-correctness, super-review-security)', definitions['super-review']['tools'])
        self.assertIn('Agent', argv[argv.index('--tools') + 1])
        child = definitions['super-review-security']
        self.assertEqual(child['tools'], ['Read', 'Grep', 'Glob'])
        self.assertEqual((child['model'], child['effort']), ('security-model', 'high'))

    def test_opencode_task_allowlist_and_child_variant(self):
        specs = agent_definitions(self.config(), 'opencode')
        _, _, env = build_command('opencode', {'command': ['opencode']}, Path('/tmp/p'), specs)
        cfg = json.loads(env['OPENCODE_CONFIG_CONTENT'])
        self.assertEqual(cfg['permission']['task']['*'], 'deny')
        self.assertEqual(cfg['permission']['task']['super-review-security'], 'allow')
        child = cfg['agent']['super-review-security']
        self.assertEqual(child['mode'], 'subagent')
        self.assertEqual(child['permission']['task'], 'deny')
        self.assertEqual((child['model'], child['variant']), ('security-model', 'high'))

    def test_opencode_child_effort_requires_a_configured_model(self):
        cfg = default_config()
        cfg['run']['harnesses'] = ['opencode']
        cfg['harnesses']['opencode']['reviewers']['security'] = {'effort': 'high'}
        with self.assertRaisesRegex(ValueError, 'model'):
            validate_config(cfg)

    def test_cursor_uses_native_readonly_roles_and_runtime_write_denies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd, logs = root / 'repo', root / 'logs'
            cwd.mkdir()
            specs = agent_definitions(self.config(), 'cursor')
            with native_workspace('cursor', specs, cwd, logs, 'parent prompt', 'shared diff'):
                text = (cwd / '.cursor/agents/super-review-security.md').read_text()
                front = {key: json.loads(value) for key, value in
                         (line.split(': ', 1) for line in text.split('---')[1].strip().splitlines())}
                self.assertEqual(front['model'], 'security-high')
                self.assertTrue(front['readonly'])
                permissions = json.loads((cwd / '.cursor/cli.json').read_text())['permissions']
                self.assertIn('Write(**)', permissions['deny'])
                self.assertIn('Shell(*)', permissions['deny'])
                argv, _, _ = build_command('cursor', {'command': ['agent']}, cwd / '.super-review-prompt.md', specs)
                self.assertNotIn('--mode', argv)
                self.assertNotIn('--trust', argv)
            self.assertEqual(list(cwd.iterdir()), [])

    def test_runtime_files_refuse_collisions_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd, logs = root / 'repo', root / 'logs'
            cwd.mkdir()
            specs = agent_definitions(self.config(), 'cursor')
            existing = cwd / '.cursor/cli.json'
            existing.parent.mkdir()
            existing.write_text('user config')
            with self.assertRaisesRegex(ValueError, 'reserved'):
                with native_workspace('cursor', specs, cwd, logs, 'prompt', 'context'):
                    self.fail('must not launch')
            self.assertEqual(existing.read_text(), 'user config')
            existing.unlink()
            existing.parent.rmdir()
            with self.assertRaisesRegex(ValueError, 'modified'):
                with native_workspace('cursor', specs, cwd, logs, 'prompt', 'context'):
                    (cwd / '.super-review-context.md').write_text('changed')
            self.assertEqual(list(cwd.iterdir()), [])
