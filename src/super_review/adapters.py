"""CLI adapters. Model output is data; the supervisor owns all report files."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal

from .prompts import COMMON
from .native import native_workspace


def build_command(harness: str, settings: dict, prompt_path: Path,
                  agents: dict | None = None,
                  native_dir: Path | None = None) -> tuple[list[str], bool, dict]:
    agents = agents or {}
    command = settings['command'].copy()
    model, effort = settings.get('model', ''), settings.get('effort', '')
    env: dict[str, str] = {}
    pointer = f'Read {prompt_path.name} completely and perform the review task it specifies.'
    if harness == 'codex':
        command += ['-a', 'never', 'exec', '--sandbox', 'read-only', '--json', '--ephemeral',
                    '-c', 'web_search="disabled"', '-c', 'features.hooks=false',
                    '-c', 'agents.enabled=' + ('true' if agents else 'false')]
        for name, definition in agents.items():
            role_path = (native_dir or Path('NATIVE_AGENT_DIR')) / f'{name}.toml'
            command += ['-c', f'agents.{name}.config_file={json.dumps(str(role_path), ensure_ascii=False)}',
                        '-c', f'agents.{name}.description={json.dumps(definition["description"], ensure_ascii=False)}']
        if model:
            command += ['--model', model]
        if effort:
            command += ['-c', f'model_reasoning_effort={json.dumps(effort, ensure_ascii=False)}']
        command += ['-']
        return command, True, env
    if harness == 'claude_code':
        tools = ['Read', 'Grep', 'Glob']
        parent_tools = tools + ([f'Agent({", ".join(agents)})'] if agents else [])
        definitions = {'super-review': {'description': 'Parent code reviewer',
                                        'prompt': COMMON, 'tools': parent_tools}}
        for name, definition in agents.items():
            child = {'description': definition['description'], 'prompt': definition['prompt'],
                     'tools': tools, 'permissionMode': 'plan'}
            for key in ('model', 'effort'):
                if definition[key]:
                    child[key] = definition[key]
            definitions[name] = child
        command += ['-p', '--output-format', 'json', '--permission-mode', 'plan',
                    '--tools', ','.join(tools + (['Agent'] if agents else [])), '--strict-mcp-config',
                    '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence',
                    '--settings', '{"disableAllHooks":true}', '--setting-sources', 'user',
                    '--disable-slash-commands', '--agents', json.dumps(definitions),
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
        command += ['--print', '--output-format', 'stream-json']
        if agents:
            command += ['--workspace', str(prompt_path.parent)]
        else:
            command += ['--mode', 'ask']
        if model:
            command += ['--model', model]
        command += [pointer]
        return command, False, env
    if harness == 'opencode':
        permissions = {'*': 'deny', 'read': 'allow', 'glob': 'allow', 'grep': 'allow',
                       'list': 'allow', 'edit': 'deny', 'bash': 'deny', 'task': 'deny',
                       'external_directory': 'deny'}
        parent_permissions = {**permissions, 'task': {'*': 'deny', **{name: 'allow' for name in agents}}} if agents else permissions
        definitions = {'super-review': {'description': 'Parent code reviewer',
                                       'mode': 'primary', 'disable': False, 'prompt': COMMON,
                                       'permission': parent_permissions}}
        for name, definition in agents.items():
            child = {'description': definition['description'], 'prompt': definition['prompt'],
                     'mode': 'subagent', 'permission': permissions}
            if definition['model']:
                child['model'] = definition['model']
            if definition['effort']:
                child['variant'] = definition['effort']
            definitions[name] = child
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps({
            'permission': parent_permissions, 'share': 'disabled',
            'autoupdate': False, 'snapshot': False,
            'agent': definitions})
        env['OPENCODE_AUTO_SHARE'] = 'false'
        env['OPENCODE_DISABLE_PROJECT_CONFIG'] = 'true'
        # Global configuration task allowlist limits the parent; children also carry an
        # explicit deny in their native definition so they cannot delegate further.
        env['OPENCODE_PERMISSION'] = json.dumps(parent_permissions)
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
                 log_dir: Path, timeout: float, max_output_bytes: int,
                 agents: dict | None = None, context: str = '') -> str:
    prompt_path = cwd / '.super-review-prompt.md'
    with native_workspace(harness, agents or {}, cwd, log_dir, prompt, context) as native_dir:
        argv, use_stdin, env = build_command(harness, settings, prompt_path, agents, native_dir)
        env['SUPER_REVIEW_WORKER'] = '1'
        (log_dir / 'command.json').write_text(json.dumps(argv, indent=2), encoding='utf-8')
        stdout, _ = await run_process(argv, prompt if use_stdin else '', cwd, env,
                                      timeout, max_output_bytes, log_dir)
        return parse_output(harness, stdout)
