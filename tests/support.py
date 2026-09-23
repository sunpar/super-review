from pathlib import Path
import subprocess


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.PIPE).strip()


def make_repo(root: Path) -> tuple[Path, str, str]:
    repo = root / 'source'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'tests@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    (repo / 'calc.py').write_text('def total(a, b):\n    return a + b\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    base = git(repo, 'rev-parse', 'HEAD')
    (repo / 'calc.py').write_text('def total(a, b):\n    return a - b\n')
    git(repo, 'commit', '-am', 'head')
    return repo, base, git(repo, 'rev-parse', 'HEAD')
