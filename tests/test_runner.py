import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import make_repo, git
from super_review.config import default_config
from super_review.protocol import digest_json
from super_review.runner import create_run, execute_run, read_status


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setup_run(self, root, harnesses, failure='none', concurrency=4):
        repo, base, head = make_repo(root)
        config = default_config()
        config['run'].update({'harnesses': harnesses, 'reviewers': ['correctness', 'security'],
                              'concurrency': concurrency, 'timeout_seconds': 10})
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

    async def test_resume_rejects_older_prompt_and_adapter_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, run, events = self.setup_run(Path(tmp), ['codex'])
            manifest_path = run / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['protocol_version'] = 1
            manifest['contract_sha256'] = digest_json({key: manifest[key] for key in (
                'protocol_version', 'run_id', 'target', 'config', 'requirements', 'diff_sha256')})
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'start a new run'):
                await execute_run(run)
            self.assertFalse(events.exists())

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

    async def test_cancellation_during_checkout_keeps_loop_responsive_and_removes_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, run, events = self.setup_run(root, ['codex'], concurrency=1)
            real_git = shutil.which('git')
            wrapper_dir = root / 'bin'
            wrapper_dir.mkdir()
            started = root / 'checkout-started.json'
            wrapper = wrapper_dir / 'git'
            # Hold an actual completed checkout open, as a slow checkout filter can.
            # The finite fallback also allows the old blocking implementation to fail.
            wrapper.write_text(f'''#!{sys.executable}
import json, os, subprocess, sys, time
from pathlib import Path
args = sys.argv[1:]
if 'worktree' in args and 'add' in args:
    subprocess.run([{real_git!r}, *args], check=True)
    Path({str(started)!r}).write_text(json.dumps({{'pid': os.getpid(), 'time': time.monotonic(), 'git_dir': os.environ.get('GIT_DIR')}}))
    time.sleep(1.5)
else:
    os.execv({real_git!r}, [{real_git!r}, *args])
''')
            wrapper.chmod(0o755)
            with patch.dict(os.environ, {'PATH': str(wrapper_dir) + os.pathsep + os.environ['PATH'],
                                         'GIT_DIR': str(repo / '.git')}):
                task = asyncio.create_task(execute_run(run))
                try:
                    async with asyncio.timeout(5):
                        while not started.exists():
                            await asyncio.sleep(.01)
                    checkout = json.loads(started.read_text())
                    observed_delay = time.monotonic() - checkout['time']
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
            self.assertLess(observed_delay, .75, 'Git checkout blocked the event loop')
            self.assertIsNone(checkout['git_dir'])
            with self.assertRaises(ProcessLookupError):
                os.kill(checkout['pid'], 0)
            self.assertFalse(list((run / 'workspaces').iterdir()))
            self.assertEqual(read_status(run)['state'], 'interrupted')
            self.assertFalse(events.exists(), 'A model was invoked before checkout completed')
            await execute_run(run)
            self.assertEqual(read_status(run)['state'], 'complete')
