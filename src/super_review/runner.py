"""Persistent dependency graph: specialist reviews -> critiques -> finals -> synthesis."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from .adapters import invoke
from .config import settings_for, validate_config
from .git import resolve_target, create_snapshot, workspace, assert_clean
from .prompts import render_prompt
from .protocol import (RunLock, atomic_write, digest_bytes, digest_json, publish,
                       utc_now, verify_artifact)

PROTOCOL_VERSION = 1
TASK_FIELDS = ('id', 'phase', 'harness', 'reviewer', 'target_harness', 'dependencies', 'output')


def plan_jobs(config: dict, run_id: str) -> dict:
    jobs = {}
    peers = config['run']['harnesses']

    def add(identity, phase, harness, output, deps=(), reviewer=None, target=None):
        jobs[identity] = {'id': identity, 'phase': phase, 'harness': harness,
                          'reviewer': reviewer, 'target_harness': target,
                          'dependencies': list(deps), 'output': output,
                          'state': 'pending', 'attempts': 0}

    # Round-robin between peers gives each a chance to finish and start critiques.
    for reviewer in config['run']['reviewers']:
        for h in peers:
            add(f'{h}.specialist.{reviewer}', 'specialist', h,
                f'specialists/{h}_{reviewer}_{run_id}.md', reviewer=reviewer)
    for h in peers:
        add(f'{h}.coordinator', 'coordinator', h, f'reviews/{h}_{run_id}.md',
            [f'{h}.specialist.{r}' for r in config['run']['reviewers']])
    critiques = []
    for h in peers:
        for other in peers:
            if h == other:
                continue
            name = f'{h}.critique.{other}'
            critiques.append(name)
            add(name, 'critique', h, f'critiques/{h}_critique_{other}_{run_id}.md',
                [f'{h}.coordinator', f'{other}.coordinator'], target=other)
    reviews = [f'{h}.coordinator' for h in peers]
    for h in peers:
        add(f'{h}.revision', 'revision', h, f'final/{h}_final_{run_id}.md', reviews + critiques)
    add('codex.synthesis', 'synthesis', 'codex', f'combined_review_{run_id}.md',
        [f'{h}.revision' for h in peers])
    return jobs


def _contract(manifest):
    return {key: manifest[key] for key in ('protocol_version', 'run_id', 'target',
                                          'config', 'requirements', 'diff_sha256')}


def create_run(repo: Path, base: str, head: str, config: dict, output_root: Path,
               requirements: str = '', merge_base: bool = True) -> Path:
    config = copy.deepcopy(validate_config(config))
    target = resolve_target(repo, base, head, merge_base)
    patch = target.pop('diff')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    root = output_root.expanduser().resolve() / run_id
    root.mkdir(parents=True, mode=0o700)
    atomic_write(root / 'diff.patch', patch)
    create_snapshot(Path(target['repository']), root / 'repository.git', target)
    n, r = len(config['run']['harnesses']), len(config['run']['reviewers'])
    manifest = {'protocol_version': PROTOCOL_VERSION, 'run_id': run_id,
                'created_at': utc_now(), 'state': 'pending', 'target': target,
                'config': config, 'requirements': requirements,
                'diff_sha256': digest_bytes(patch.encode('utf-8')),
                'expected': {'specialists': n*r, 'reviews': n, 'critiques': n*(n-1),
                             'final_reviews': n, 'combined_reviews': 1},
                'jobs': plan_jobs(config, run_id)}
    manifest['contract_sha256'] = digest_json(_contract(manifest))
    _save(root, manifest)
    return root


def _save(root, manifest):
    manifest['updated_at'] = utc_now()
    atomic_write(root / 'manifest.json', json.dumps(manifest, indent=2) + '\n')


def _read(root: Path) -> dict:
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['protocol_version'] != PROTOCOL_VERSION:
            raise ValueError('Unsupported protocol version')
        if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}', manifest['run_id']):
            raise ValueError('Invalid run ID')
        validate_config(manifest['config'])
        if digest_json(_contract(manifest)) != manifest['contract_sha256']:
            raise ValueError('Run contract hash mismatch; start a new run to change inputs')
        expected = plan_jobs(manifest['config'], manifest['run_id'])
        if set(manifest['jobs']) != set(expected):
            raise ValueError('Manifest job set does not match run configuration')
        for name, task in manifest['jobs'].items():
            if any(task[key] != expected[name][key] for key in TASK_FIELDS):
                raise ValueError('Manifest job identity does not match run configuration')
        return manifest
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid run manifest') from exc


def read_status(root: Path) -> dict:
    manifest = _read(root)
    return {'run_id': manifest['run_id'], 'state': manifest['state'],
            'expected': manifest['expected'],
            'completed': sum(t['state'] == 'completed' for t in manifest['jobs'].values()),
            'total': len(manifest['jobs']),
            'jobs': {k: {field: v.get(field) for field in ('state', 'attempts', 'error')}
                     for k, v in manifest['jobs'].items()}}


def _metadata(manifest, task):
    settings = settings_for(manifest['config'], task['harness'], task['phase'], task['reviewer'])
    model = settings.get('model')
    if task['harness'] == 'cursor' and settings.get('effort'):
        model = settings['effort_models'][settings['effort']]
    return {'review_protocol': PROTOCOL_VERSION, 'run_id': manifest['run_id'],
            'job_id': task['id'], 'phase': task['phase'], 'author_harness': task['harness'],
            'reviewer': task['reviewer'], 'target_harness': task['target_harness'],
            'base_sha': manifest['target']['base_sha'], 'head_sha': manifest['target']['head_sha'],
            'contract_sha256': manifest['contract_sha256'],
            'model': model or '(CLI default)',
            'effort': settings.get('effort') or '(CLI default)'}


def _reports(root, manifest, task):
    deps = task['dependencies']
    if task['phase'] == 'revision':
        # The global critique barrier is wider than this job's input context.
        deps = [f"{task['harness']}.coordinator"] + [name for name in deps
                if manifest['jobs'][name]['phase'] == 'critique'
                and manifest['jobs'][name]['target_harness'] == task['harness']]
    return {name: verify_artifact(root / manifest['jobs'][name]['output'],
                                 _metadata(manifest, manifest['jobs'][name]),
                                 manifest['jobs'][name]['sha256']) for name in deps}


async def _job(root, manifest, task, patch):
    config = manifest['config']
    settings = settings_for(config, task['harness'], task['phase'], task['reviewer'])
    prompt = render_prompt(manifest, task, patch, _reports(root, manifest, task))
    # Per-attempt random directories avoid reusing a worktree left by SIGKILL.
    workdir = root / 'workspaces' / f"{task['id']}-{uuid.uuid4().hex[:8]}"
    logs = root / 'logs' / task['id'] / str(task['attempts'])
    with workspace(root / 'repository.git', workdir, manifest['target']['head_sha']) as cwd:
        body = await invoke(task['harness'], settings, prompt, cwd, logs,
                            config['run']['timeout_seconds'], config['run']['max_output_bytes'])
        assert_clean(cwd, manifest['target']['head_sha'])
    metadata = {**_metadata(manifest, task), 'generated_at': utc_now()}
    return publish(root / task['output'], metadata, body)


async def execute_run(root: Path, progress=None) -> Path:
    root = root.resolve()
    with RunLock(root):
        manifest = _read(root)
        patch = (root / 'diff.patch').read_text(encoding='utf-8')
        if digest_bytes(patch.encode('utf-8')) != manifest['diff_sha256']:
            raise ValueError('Pinned diff hash mismatch')
        jobs = manifest['jobs']
        for task in jobs.values():
            if task['state'] == 'completed':
                verify_artifact(root / task['output'], _metadata(manifest, task), task['sha256'])
                if any(jobs[d]['state'] != 'completed' for d in task['dependencies']):
                    raise ValueError('Completed report has incomplete dependencies')
            else:
                task['state'] = 'pending'
        if all(t['state'] == 'completed' for t in jobs.values()):
            manifest['state'] = 'complete'
            _save(root, manifest)
            return root / jobs['codex.synthesis']['output']
        manifest['state'] = 'running'
        _save(root, manifest)
        active = {}
        limit = manifest['config']['run']['concurrency']
        priority = {'critique': 0, 'coordinator': 1, 'revision': 2, 'synthesis': 3, 'specialist': 4}
        try:
            async with asyncio.timeout(manifest['config']['run']['total_timeout_seconds']):
                while any(t['state'] != 'completed' for t in jobs.values()):
                    ready = [t for t in jobs.values() if t['state'] == 'pending'
                             and all(jobs[d]['state'] == 'completed' for d in t['dependencies'])]
                    ready.sort(key=lambda t: priority[t['phase']])
                    for task in ready[:limit - len(active)]:
                        task.update(state='running', attempts=task['attempts'] + 1,
                                    started_at=utc_now(), error=None)
                        active[asyncio.create_task(_job(root, manifest, task, patch))] = task
                        if progress:
                            progress(f"Starting {task['id']} (attempt {task['attempts']})")
                    _save(root, manifest)
                    if not active:
                        raise RuntimeError('No runnable jobs; dependency graph is incomplete')
                    done, _ = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                    errors = []
                    for future in done:
                        task = active.pop(future)
                        try:
                            task['sha256'] = future.result()
                            task.update(state='completed', finished_at=utc_now())
                            if progress:
                                progress(f"Completed {task['id']}")
                        except Exception as exc:
                            task.update(state='failed', error=f'{type(exc).__name__}: {exc}')
                            errors.append(f"{task['id']}: {task['error']}")
                    _save(root, manifest)
                    if errors:
                        raise RuntimeError('; '.join(errors))
        except BaseException as exc:
            for future in active:
                future.cancel()
            await asyncio.gather(*active, return_exceptions=True)
            for task in active.values():
                task.update(state='pending', error='Interrupted; safe to resume')
            manifest['state'] = 'interrupted' if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else 'failed'
            manifest['error'] = f'{type(exc).__name__}: {exc}'
            _save(root, manifest)
            raise
        manifest.update(state='complete', error=None, completed_at=utc_now())
        _save(root, manifest)
        return root / jobs['codex.synthesis']['output']
