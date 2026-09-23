import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from super_review.adapters import build_command, parse_output, run_process


class AdapterTests(unittest.TestCase):
    def test_effort_is_translated_without_shell_interpolation(self):
        cfg = {'command': ['codex'], 'model': 'model name', 'effort': 'high'}
        argv, stdin, _ = build_command('codex', cfg, Path('/tmp/prompt.md'))
        self.assertIn('model name', argv)
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertIn('read-only', argv)
        self.assertTrue(stdin)
        cfg['command'] = ['claude']
        argv, _, _ = build_command('claude_code', cfg, Path('/tmp/prompt.md'))
        self.assertIn('--effort', argv)
        self.assertIn('Read,Grep,Glob', argv)
        cfg['command'] = ['opencode']
        argv, _, env = build_command('opencode', cfg, Path('/tmp/prompt.md'))
        self.assertIn('--variant', argv)
        self.assertEqual(json.loads(env['OPENCODE_CONFIG_CONTENT'])['permission']['edit'], 'deny')

    def test_cursor_effort_is_an_explicit_model_id(self):
        argv, _, _ = build_command('cursor', {'command': ['agent'], 'model': 'base',
                 'effort': 'high', 'effort_models': {'high': 'model-high'}}, Path('/tmp/p.md'))
        self.assertEqual(argv[argv.index('--model') + 1], 'model-high')
        self.assertEqual(argv[argv.index('--mode') + 1], 'ask')

    def test_extract_only_final_messages_not_tool_logs(self):
        codex = '\n'.join(json.dumps(x) for x in [
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'aggregated_output': 'secret'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Review\nA finding'}},
            {'type': 'turn.completed', 'usage': {}}])
        self.assertEqual(parse_output('codex', codex), '# Review\nA finding')
        for h in ('claude_code', 'cursor'):
            self.assertEqual(parse_output(h, json.dumps({'type': 'result', 'subtype': 'success',
                     'is_error': False, 'result': '# Review'})), '# Review')
        oc = '\n'.join(json.dumps(x) for x in [
            {'type': 'text', 'part': {'type': 'text', 'text': '# Review'}},
            {'type': 'step_finish', 'part': {'reason': 'stop'}}])
        self.assertEqual(parse_output('opencode', oc), '# Review')

    def test_failures_and_truncated_streams_are_not_reviews(self):
        for h, response in [
            ('claude_code', {'type': 'result', 'is_error': True, 'result': 'API failure'}),
            ('cursor', {'type': 'result', 'subtype': 'error', 'result': 'bad'}),
            ('codex', {'type': 'turn.failed', 'error': {'message': 'failed'}}),
            ('opencode', {'type': 'error', 'error': {'message': 'failed'}}),
            ('codex', {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial'}}),
            ('opencode', {'type': 'text', 'part': {'text': 'partial'}}),
        ]:
            with self.subTest(h=h, response=response), self.assertRaises(ValueError):
                parse_output(h, json.dumps(response))

    def test_cursor_report_excludes_progress_text(self):
        events = [
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'I will inspect files.'}]}},
            {'type': 'tool_call', 'subtype': 'completed', 'call_id': 'one', 'tool_call': {}},
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': '# Final review'}]}},
            {'type': 'result', 'subtype': 'success', 'is_error': False,
             'result': 'I will inspect files.# Final review', 'session_id': 'session'}]
        self.assertEqual(parse_output('cursor', '\n'.join(json.dumps(x) for x in events)), '# Final review')

    def test_opencode_report_excludes_prior_tool_steps(self):
        events = [
            {'type': 'step_start', 'part': {'type': 'step-start'}},
            {'type': 'text', 'part': {'text': 'Let me inspect files.'}},
            {'type': 'step_finish', 'part': {'reason': 'tool-calls'}},
            {'type': 'step_start', 'part': {'type': 'step-start'}},
            {'type': 'text', 'part': {'text': '# Final review'}},
            {'type': 'step_finish', 'part': {'reason': 'stop'}}]
        self.assertEqual(parse_output('opencode', '\n'.join(json.dumps(x) for x in events)), '# Final review')


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_subprocess_receives_stdin(self):
        out, err = await run_process([sys.executable, '-c',
            'import sys;print(sys.stdin.read().upper())'], 'hello', Path.cwd(), {}, 5, 4096)
        self.assertEqual(out.strip(), 'HELLO')
        self.assertEqual(err, '')

    async def test_timeout_and_output_limit_are_failures(self):
        with self.assertRaises(TimeoutError):
            await run_process([sys.executable, '-c', 'import time;time.sleep(20)'], '',
                              Path.cwd(), {}, .1, 4096)
        with self.assertRaisesRegex(ValueError, 'output'):
            await run_process([sys.executable, '-c', 'print("x"*100000)'], '',
                              Path.cwd(), {}, 5, 4096)

    async def test_nonzero_exit_is_failure_even_with_stdout(self):
        with self.assertRaisesRegex(RuntimeError, 'exit code 7'):
            await run_process([sys.executable, '-c', 'print("report");exit(7)'], '',
                              Path.cwd(), {}, 5, 4096)
