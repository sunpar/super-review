import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import make_repo, git
from super_review.config import default_config
from super_review.runner import create_run, execute_run, read_status


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setup_run(self, root, harnesses, failure='none'):
        repo, base, head = make_repo(root)
        config = default_config()
        config['run'].update({'harnesses': harnesses, 'reviewers': ['correctness', 'security'],
                              'concurrency': 4, 'timeout_seconds': 10})
        events = root / 'events.jsonl'
        for h in config['harnesses']:
            config['harnesses'][h]['command'] = [sys.executable,
                str(Path(__file__).with_name('fake_harness.py')), h, str(events), failure]
        run = create_run(repo, base, head, config, root / 'runs', requirements='Use addition.')
        return repo, run, events

    async def test_four_harnesses_all_directed_critiques_and_barriers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, run, events = self.setup_run(root, ['codex', 'claude_code', 'cursor', 'opencode'], 'slow-opencode')
            result = await execute_run(run)
            self.assertTrue(result.is_file())
            state = read_status(run)
            self.assertEqual(state['state'], 'complete')
            self.assertEqual(state['expected'], {'specialists': 8, 'reviews': 4, 'critiques': 12,
                                               'final_reviews': 4, 'combined_reviews': 1})
            records = [json.loads(x) for x in events.read_text().splitlines()]
            starts = {r['job']: r['time'] for r in records if r['event'] == 'start'}
            ends = {r['job']: r['time'] for r in records if r['event'] == 'end'}
            critique_ends = [r['time'] for r in records if r['event'] == 'end' and r['phase'] == 'critique']
            for r in records:
                if r['event'] == 'start' and r['phase'] == 'revision':
                    self.assertGreater(r['time'], max(critique_ends))
            self.assertLess(starts['codex.critique.claude_code'], ends['opencode.coordinator'])
            active = maximum = 0
            for r in sorted(records, key=lambda x: x['time']):
                active += 1 if r['event'] == 'start' else -1
                maximum = max(maximum, active)
            self.assertLessEqual(maximum, 4)
            self.assertGreater(maximum, 1)
            self.assertEqual(git(repo, 'status', '--porcelain'), '')
            self.assertFalse(list((run / 'workspaces').iterdir()))
            before = events.read_text()
            await execute_run(run)
            self.assertEqual(events.read_text(), before)

    async def test_resume_retains_completed_work_and_retries_failed_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, run, events = self.setup_run(Path(tmp), ['codex', 'claude_code'], 'codex.critique.claude_code')
            with self.assertRaises(RuntimeError):
                await execute_run(run)
            self.assertEqual(read_status(run)['state'], 'failed')
            before = json.loads((run / 'manifest.json').read_text())
            completed = {k: v['sha256'] for k, v in before['jobs'].items() if v['state'] == 'completed'}
            await execute_run(run)
            after = json.loads((run / 'manifest.json').read_text())
            for name, sha in completed.items():
                self.assertEqual(after['jobs'][name]['sha256'], sha)
            self.assertEqual(after['jobs']['codex.critique.claude_code']['attempts'], 2)

    async def test_tampered_artifact_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, run, events = self.setup_run(Path(tmp), ['codex'])
            result = await execute_run(run)
            result.write_text(result.read_text() + 'altered')
            before = events.read_text()
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                await execute_run(run)
            self.assertEqual(events.read_text(), before)

    async def test_workspace_edits_are_rejected_and_original_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, run, events = self.setup_run(Path(tmp), ['codex'], 'modify-source')
            original = (repo / 'calc.py').read_text()
            with self.assertRaises(RuntimeError):
                await execute_run(run)
            self.assertEqual((repo / 'calc.py').read_text(), original)
            self.assertFalse(list(run.glob('combined_review*')))

    async def test_codex_synthesizes_even_when_not_review_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, run, events = self.setup_run(Path(tmp), ['claude_code'])
            await execute_run(run)
            records = [json.loads(x) for x in events.read_text().splitlines()]
            self.assertEqual([x['phase'] for x in records if x['harness'] == 'codex' and x['event'] == 'start'], ['synthesis'])
