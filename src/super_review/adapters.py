"""CLI adapters. Model output is data; the supervisor owns all report files."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal

from .prompts import COMMON


def build_command(harness: str, settings: dict, prompt_path: Path) -> tuple[list[str], bool, dict]:
    command = settings['command'].copy()
    model, effort = settings.get('model', ''), settings.get('effort', '')
    env: dict[str, str] = {}
    pointer = f'Read {prompt_path.name} completely and perform the review task it specifies.'
    if harness == 'codex':
        command += ['-a', 'never', 'exec', '--sandbox', 'read-only', '--json', '--ephemeral',
                    '-c', 'web_search="disabled"', '-c', 'features.hooks=false',
                    '-c', 'features.multi_agent=false']
        if model:
            command += ['--model', model]
        if effort:
            command += ['-c', f'model_reasoning_effort={json.dumps(effort)}']
        command += ['-']
        return command, True, env
    if harness == 'claude_code':
        agents = {'super-review': {'description': 'Independent read-only code reviewer',
                                   'prompt': COMMON, 'tools': ['Read', 'Grep', 'Glob']}}
        command += ['-p', '--output-format', 'json', '--permission-mode', 'plan',
                    '--tools', 'Read,Grep,Glob', '--strict-mcp-config',
                    '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence',
                    '--settings', '{"disableAllHooks":true}', '--setting-sources', 'user',
                    '--disable-slash-commands', '--agents', json.dumps(agents),
                    '--agent', 'super-review']
        if model:
            command += ['--model', model]
        if effort:
            command += ['--effort', effort]
        return command, True, env
    if harness == 'cursor':
        if effort:
            try:
                model = settings['effort_models'][effort]
            except KeyError as exc:
                raise ValueError('Cursor effort requires effort_models') from exc
        command += ['--print', '--mode', 'ask', '--output-format', 'stream-json']
        if model:
            command += ['--model', model]
        command += [pointer]
        return command, False, env
    if harness == 'opencode':
        permissions = {'*': 'deny', 'read': 'allow', 'glob': 'allow', 'grep': 'allow',
                       'list': 'allow', 'edit': 'deny', 'bash': 'deny', 'task': 'deny',
                       'external_directory': 'deny'}
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps({
            'permission': permissions, 'share': 'disabled',
            'autoupdate': False, 'snapshot': False,
            'agent': {'super-review': {'description': 'Read-only code reviewer',
                                      'mode': 'primary', 'disable': False, 'prompt': COMMON,
                                      'permission': permissions}}})
        env['OPENCODE_AUTO_SHARE'] = 'false'
        env['OPENCODE_DISABLE_PROJECT_CONFIG'] = 'true'
        env['OPENCODE_PERMISSION'] = json.dumps(permissions)
        command += ['run', '--format', 'json', '--agent', 'super-review']
        if model:
            command += ['--model', model]
        if effort:
            command += ['--variant', effort]
        command += [pointer]
        return command, False, env
    raise ValueError(f'Unsupported harness: {harness}')


def parse_output(harness: str, stdout: str) -> str:
    """Reject failed/incomplete envelopes instead of publishing their error prose."""
    if harness == 'claude_code':
        try:
            obj = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f'{harness}: expected one JSON result') from exc
        if not isinstance(obj, dict) or obj.get('type') != 'result':
            raise ValueError(f'{harness}: missing result envelope')
        if obj.get('is_error') or obj.get('subtype') != 'success':
            raise ValueError(f'{harness}: unsuccessful result: {obj.get("subtype", "error")}')
        result = obj.get('result')
    else:
        events = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'{harness}: invalid JSON event stream') from exc
            if not isinstance(obj, dict):
                raise ValueError(f'{harness}: invalid event')
            if obj.get('type') in ('error', 'turn.failed'):
                raise ValueError(f'{harness}: error event in output')
            events.append(obj)
        if harness == 'codex':
            result, completed = '', False
            for event in events:
                if event.get('type') == 'turn.started':
                    result, completed = '', False
                elif (event.get('type') == 'item.completed'
                      and isinstance(event.get('item'), dict)
                      and event['item'].get('type') == 'agent_message'
                      and isinstance(event['item'].get('text'), str)):
                    result, completed = event['item']['text'], False
                elif event.get('type') == 'turn.completed':
                    completed = True
            if not completed:
                raise ValueError('codex: incomplete turn')
        elif harness == 'cursor':
            terminal = events[-1] if events else {}
            if (terminal.get('type') != 'result' or terminal.get('subtype') != 'success'
                    or terminal.get('is_error')):
                raise ValueError('cursor: missing successful terminal result')
            result = terminal.get('result')
        elif harness == 'opencode':
            chunks, stopped = [], False
            for event in events:
                part = event.get('part')
                if event.get('type') == 'step_start':
                    chunks, stopped = [], False
                elif event.get('type') == 'text' and isinstance(part, dict) and isinstance(part.get('text'), str):
                    chunks.append(part['text'])
                    stopped = False
                elif event.get('type') == 'step_finish' and isinstance(part, dict):
                    stopped = part.get('reason') == 'stop'
            if not stopped:
                raise ValueError('opencode: incomplete turn (no stop event)')
            result = '\n'.join(chunks)
        else:
            raise ValueError(f'Unsupported harness: {harness}')
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f'{harness}: empty report')
    return result.strip()


async def run_process(argv: list[str], stdin: str, cwd: Path, env: dict,
                      timeout: float, max_output_bytes: int,
                      log_dir: Path | None = None, *, inherit_env: bool = True) -> tuple[str, str]:
    """Bound time/output and reap the entire process group on failure/cancellation."""
    if os.name != 'posix':
        raise RuntimeError('Use Linux, macOS, or WSL (POSIX process groups are required)')
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=cwd,
        env={**os.environ, **env} if inherit_env else env,
        start_new_session=True))
    try:
        process = await asyncio.shield(spawning)
    except asyncio.CancelledError as cancelled:
        # Cancellation can arrive after fork but before asyncio returns the handle.
        # Finish obtaining ownership before terminating and draining that process.
        try:
            process = await spawning
        except Exception:
            raise cancelled
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.communicate()
        raise
    captured = [bytearray(), bytearray()]

    async def drain(stream, index):
        while chunk := await stream.read(65536):
            captured[index].extend(chunk)
            if sum(len(x) for x in captured) > max_output_bytes:
                raise ValueError('Harness output exceeded max_output_bytes')

    async def feed():
        try:
            process.stdin.write(stdin.encode('utf-8'))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    tasks = [asyncio.create_task(feed()),
             asyncio.create_task(drain(process.stdout, 0)),
             asyncio.create_task(drain(process.stderr, 1)),
             asyncio.create_task(process.wait())]
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(*tasks)
        if process.returncode:
            raise RuntimeError(f'Harness exited with exit code {process.returncode}; inspect task logs')
    finally:
        # Reap children even if their parent exited first. Never use shell kill strings.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await process.wait()
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            for name, data in zip(('stdout.log', 'stderr.log'), captured):
                (log_dir / name).write_bytes(data[:max_output_bytes])
    return tuple(x.decode('utf-8', errors='replace') for x in captured)


async def invoke(harness: str, settings: dict, prompt: str, cwd: Path,
                 log_dir: Path, timeout: float, max_output_bytes: int) -> str:
    prompt_path = cwd / '.super-review-prompt.md'
    if prompt_path.exists():
        raise ValueError('Reviewed repository contains reserved .super-review-prompt.md')
    prompt_path.write_text(prompt, encoding='utf-8')
    argv, use_stdin, env = build_command(harness, settings, prompt_path)
    env['SUPER_REVIEW_WORKER'] = '1'
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / 'command.json').write_text(json.dumps(argv, indent=2), encoding='utf-8')
    try:
        stdout, _ = await run_process(argv, prompt if use_stdin else '', cwd, env,
                                      timeout, max_output_bytes, log_dir)
        return parse_output(harness, stdout)
    finally:
        prompt_path.unlink(missing_ok=True)
