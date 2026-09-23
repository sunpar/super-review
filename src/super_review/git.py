"""Pin committed targets and keep harness workspaces separate from the source."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess


def git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update({'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'})
    result = subprocess.run(['git', '--no-replace-objects', '-c', 'core.hooksPath=/dev/null',
                             '-c', 'core.quotePath=false', '-C', str(repo), *args],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            env=env, timeout=120)
    if result.returncode:
        raise ValueError(f'Git {args[0]} failed: {result.stderr.strip()}')
    return result.stdout.rstrip('\n')


def diff(repo: Path, base: str, head: str) -> str:
    return git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--binary',
               '--no-color', '--find-renames', base, head, '--')


def resolve_target(repo: Path, base: str, head: str, merge_base: bool = True) -> dict:
    for ref in (base, head):
        if not ref or ref.startswith('-') or '\x00' in ref:
            raise ValueError('Git references must be nonempty and cannot start with -')
    repo = Path(git(repo.resolve(), 'rev-parse', '--show-toplevel'))
    base_sha = git(repo, 'rev-parse', '--verify', f'{base}^{{commit}}')
    head_sha = git(repo, 'rev-parse', '--verify', f'{head}^{{commit}}')
    merge = git(repo, 'merge-base', base_sha, head_sha) if merge_base else base_sha
    patch = diff(repo, merge, head_sha)
    if not patch:
        raise ValueError('No committed changes in the selected range')
    raw = git(repo, 'diff', '--raw', '--no-abbrev', merge, head_sha, '--')
    if any('160000' in line.lstrip(':').split('\t')[0].split()[:2] for line in raw.splitlines()):
        raise ValueError('Changed submodules are not supported; review each submodule separately')
    if git(repo, 'ls-tree', '--name-only', head_sha, '--', '.super-review-prompt.md'):
        raise ValueError('Repository uses reserved .super-review-prompt.md filename')
    return {'repository': str(repo), 'requested_base': base, 'requested_head': head,
            'base_ref_sha': base_sha, 'base_sha': merge, 'head_sha': head_sha,
            'merge_base': merge, 'dirty_source': bool(git(repo, 'status', '--porcelain')),
            'diff': patch}


def create_snapshot(repo: Path, snapshot: Path, target: dict) -> None:
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    git(snapshot.parent, 'clone', '--mirror', '--no-hardlinks', '--local', '--dissociate',
        str(repo.resolve()), str(snapshot.resolve()))
    git(snapshot, 'remote', 'remove', 'origin')
    for name in ('base_sha', 'head_sha'):
        git(snapshot, 'cat-file', '-e', target[name] + '^{commit}')
        git(snapshot, 'update-ref', f'refs/super-review/{name}', target[name])


@contextmanager
def workspace(snapshot: Path, path: Path, head: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f'Unexpected existing worktree: {path}')
    git(snapshot, 'worktree', 'add', '--detach', str(path.resolve()), head)
    try:
        yield path
    finally:
        git(snapshot, 'worktree', 'remove', '--force', str(path.resolve()))


def assert_clean(path: Path, head: str) -> None:
    if (git(path, 'rev-parse', 'HEAD') != head
            or git(path, 'diff', '--no-ext-diff', '--no-textconv', head, '--')
            or git(path, 'ls-files', '--others')):
        raise ValueError('Harness modified its review workspace; report was not accepted')
