"""Console interface; orchestration never relies on a model to wait or count files."""

from __future__ import annotations

import argparse
import asyncio
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import __version__
from .adapters import build_command, run_process
from .config import load_config, settings_for, validate_config
from .git import resolve_target
from .runner import create_run, execute_run, plan_jobs, read_status


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='super-review', description='Multi-harness independent code review')
    p.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    commands = p.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Write an editable TOML configuration')
    init.add_argument('--path', type=Path, default=Path('super-review.toml'))
    doctor = commands.add_parser('doctor', help='Check configured CLI executables and versions (no model calls)')
    run = commands.add_parser('run', help='Review committed changes')
    for sub in (doctor, run):
        sub.add_argument('--config', type=Path)
        sub.add_argument('--harnesses', help='Comma-separated peer harnesses; Codex also performs synthesis')
    run.add_argument('--repo', type=Path, default=Path.cwd())
    run.add_argument('--base', required=True, help='Base Git ref; defaults to its merge-base with head')
    run.add_argument('--head', default='HEAD')
    run.add_argument('--exact-base', action='store_true', help='Compare base directly instead of merge-base')
    run.add_argument('--reviewers', help='Comma-separated specialties (default: all ten)')
    run.add_argument('--requirements', type=Path, help='UTF-8 requirements/specification file')
    run.add_argument('--intent', default='', help='Short description of the intended change')
    run.add_argument('--output', type=Path, help='Parent directory for timestamped runs')
    run.add_argument('--dry-run', action='store_true', help='Print plan and argv without calling models or creating files')
    run.add_argument('--concurrency', type=int)
    for command in ('resume', 'status'):
        sub = commands.add_parser(command, help=f'{command.title()} an existing run directory')
        sub.add_argument('run_directory', type=Path)
    return p


def _config(args):
    path = args.config
    if path is None and Path('super-review.toml').is_file():
        path = Path('super-review.toml')
    cfg = load_config(path)
    if args.harnesses is not None:
        cfg['run']['harnesses'] = [h.strip() for h in args.harnesses.split(',')]
    if getattr(args, 'reviewers', None) is not None:
        cfg['run']['reviewers'] = [r.strip() for r in args.reviewers.split(',')]
    if getattr(args, 'concurrency', None) is not None:
        cfg['run']['concurrency'] = args.concurrency
    return validate_config(cfg)


def _required(cfg):
    return list(dict.fromkeys([*cfg['run']['harnesses'], 'codex']))


def _check_binaries(cfg):
    missing = [f"{h}: {cfg['harnesses'][h]['command'][0]}" for h in _required(cfg)
               if shutil.which(cfg['harnesses'][h]['command'][0]) is None]
    if missing:
        raise ValueError('Missing harness executables: ' + ', '.join(missing) + '. Run super-review doctor.')


async def _doctor(cfg):
    ok = True
    for harness in _required(cfg):
        command = cfg['harnesses'][harness]['command']
        executable = shutil.which(command[0])
        if executable is None:
            print(f'{harness}: MISSING ({command[0]})')
            ok = False
            continue
        try:
            out, _ = await run_process([*command, '--version'], '', Path.cwd(), {}, 10, 65536)
            print(f'{harness}: {executable} | {out.strip()}')
        except (RuntimeError, ValueError, TimeoutError, OSError) as exc:
            print(f'{harness}: FAILED version check ({exc})')
            ok = False
    print('Version checks do not validate login, model access, or provider effort support.')
    return 0 if ok else 1


def _progress(message):
    print(message, file=sys.stderr, flush=True)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == 'init':
            template = files('super_review').joinpath('example.toml').read_text(encoding='utf-8')
            with args.path.open('x', encoding='utf-8') as stream:
                stream.write(template)
            print(args.path.resolve())
            return 0
        if args.command == 'status':
            print(json.dumps(read_status(args.run_directory), indent=2))
            return 0
        if args.command == 'resume':
            result = asyncio.run(execute_run(args.run_directory, _progress))
            print(result)
            return 0
        cfg = _config(args)
        if args.command == 'doctor':
            return asyncio.run(_doctor(cfg))
        requirements = args.intent
        if args.requirements:
            requirements += '\n\n' + args.requirements.read_text(encoding='utf-8')
        if args.dry_run:
            target = resolve_target(args.repo, args.base, args.head, not args.exact_base)
            target.pop('diff')
            jobs = plan_jobs(cfg, 'RUN_ID')
            plan = {'target': target, 'total_jobs': len(jobs),
                    'concurrency': cfg['run']['concurrency'], 'jobs': []}
            for task in jobs.values():
                settings = settings_for(cfg, task['harness'], task['phase'], task['reviewer'])
                cmd, stdin, _ = build_command(task['harness'], settings, Path('.super-review-prompt.md'))
                plan['jobs'].append({**{k: task[k] for k in ('id', 'dependencies', 'output')},
                                     'argv': cmd, 'prompt_on_stdin': stdin})
            print(json.dumps(plan, indent=2))
            return 0
        _check_binaries(cfg)
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
        output = args.output or Path(cfg['run']['output_root'] or cache / 'super-review' / 'runs')
        run = create_run(args.repo, args.base, args.head, cfg, output, requirements.strip(), not args.exact_base)
        _progress(f'Run directory: {run}')
        if read_status(run)['total'] >= 50:
            _progress(f"Full panel: {read_status(run)['total']} model calls before retries.")
        try:
            result = asyncio.run(execute_run(run, _progress))
        except BaseException:
            _progress(f'Resume with: super-review resume {run}')
            raise
        print(result)
        return 0
    except KeyboardInterrupt:
        print('Interrupted. Completed reports are retained for resume.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
