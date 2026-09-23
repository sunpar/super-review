import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from super_review.adapters import build_command, parse_output, run_process


class AdapterTests(unittest.TestCase):
    def test_codex_disables_persistence_and_optional_execution_features(self):
        argv, stdin, _ = build_command('codex', {'command': ['codex']}, Path('/tmp/prompt.md'))
        self.assertTrue(stdin)
        self.assertIn('--ephemeral', argv)
        overrides = [argv[i + 1] for i, arg in enumerate(argv) if arg == '-c']
        self.assertIn('web_search="disabled"', overrides)
        self.assertIn('features.hooks=false', overrides)
        self.assertIn('features.multi_agent=false', overrides)

    def test_claude_activates_read_only_agent_without_changing_login_mode(self):
        argv, stdin, _ = build_command('claude_code', {'command': ['claude']}, Path('/tmp/prompt.md'))
        self.assertTrue(stdin)
        self.assertIn('--agents', argv)
        agent_name = argv[argv.index('--agent') + 1]
        agent = json.loads(argv[argv.index('--agents') + 1])[agent_name]
        self.assertEqual(agent['tools'], ['Read', 'Grep', 'Glob'])
        self.assertTrue(agent['prompt'].strip())
        self.assertEqual(argv[argv.index('--setting-sources') + 1], 'user')
        self.assertIn('--disable-slash-commands', argv)
        self.assertNotIn('--bare', argv)

    def test_opencode_blocks_project_configuration_and_automatic_sharing(self):
        argv, stdin, env = build_command('opencode', {'command': ['opencode']}, Path('/tmp/prompt.md'))
        self.assertFalse(stdin)
        self.assertNotIn('--pure', argv)
        config = json.loads(env['OPENCODE_CONFIG_CONTENT'])
        self.assertEqual(config.get('share'), 'disabled')
        self.assertFalse(config['autoupdate'])
        self.assertFalse(config['snapshot'])
        agent = config['agent'][argv[argv.index('--agent') + 1]]
        self.assertEqual(agent['mode'], 'primary')
        self.assertFalse(agent['disable'])
        self.assertTrue(agent['prompt'].strip())
        self.assertEqual(config['permission']['task'], 'deny')
        self.assertEqual(agent['permission'], config['permission'])
        self.assertEqual(json.loads(env['OPENCODE_PERMISSION']), config['permission'])
        self.assertEqual(env['OPENCODE_AUTO_SHARE'], 'false')
        self.assertEqual(env['OPENCODE_DISABLE_PROJECT_CONFIG'], 'true')

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

    def test_cursor_report_uses_authoritative_terminal_result(self):
        events = [
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'I will inspect files.'}]}},
            {'type': 'tool_call', 'subtype': 'completed', 'call_id': 'one', 'tool_call': {}},
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': '# Final review'}]}},
            {'type': 'result', 'subtype': 'success', 'is_error': False,
             'result': 'I will inspect files.# Final review', 'session_id': 'session'}]
        self.assertEqual(parse_output('cursor', '\n'.join(json.dumps(x) for x in events)),
                         'I will inspect files.# Final review')

    def test_cursor_rejects_missing_or_empty_terminal_text_despite_assistant_text(self):
        for result in (None, '', '   ', 123):
            with self.subTest(result=result):
                terminal = {'type': 'result', 'subtype': 'success', 'is_error': False}
                if result is not None:
                    terminal['result'] = result
                events = [
                    {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '# Partial review'}]}},
                    terminal]
                with self.assertRaisesRegex(ValueError, 'empty report'):
                    parse_output('cursor', '\n'.join(json.dumps(x) for x in events))

    def test_codex_requires_success_after_latest_turn_and_report(self):
        completed = [
            {'type': 'turn.started'},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Earlier review'}},
            {'type': 'turn.completed', 'usage': {}}]
        tails = [
            [{'type': 'turn.started'}],
            [{'type': 'turn.started'},
             {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Partial review'}}],
            [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Unfinished review'}}],
            [{'type': 'turn.started'}, {'type': 'turn.completed', 'usage': {}}],
        ]
        for tail in tails:
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                parse_output('codex', '\n'.join(json.dumps(x) for x in completed + tail))

    def test_codex_selects_report_from_latest_successful_turn(self):
        events = [
            {'type': 'turn.started'},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Earlier review'}},
            {'type': 'turn.completed', 'usage': {}},
            {'type': 'turn.started'},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '# Final review'}},
            {'type': 'turn.completed', 'usage': {}}]
        self.assertEqual(parse_output('codex', '\n'.join(json.dumps(x) for x in events)), '# Final review')

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
    async def test_cancellation_during_spawn_reaps_the_created_process(self):
        real_spawn = asyncio.create_subprocess_exec
        spawned = asyncio.Event()
        release = asyncio.Event()
        process = None

        async def delayed_spawn(*args, **kwargs):
            nonlocal process
            process = await real_spawn(*args, **kwargs)
            spawned.set()
            await release.wait()
            return process

        try:
            with patch('super_review.adapters.asyncio.create_subprocess_exec', delayed_spawn):
                task = asyncio.create_task(run_process([sys.executable, '-c',
                    'import time; time.sleep(30)'], '', Path.cwd(), {}, 5, 4096))
                await asyncio.wait_for(spawned.wait(), 5)
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertIsNotNone(process.returncode, 'Cancellation leaked the started process')
            with self.assertRaises(ProcessLookupError):
                os.killpg(process.pid, 0)
        finally:
            if process is not None and process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()

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
