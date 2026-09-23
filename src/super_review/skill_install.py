"""Install shared harness skills without overwriting user edits silently."""

from importlib.resources import files
from pathlib import Path
import shutil
import tempfile
import uuid


HARNESS_NAMES = ('codex', 'claude_code', 'cursor', 'opencode')


def _contents() -> dict[str, bytes]:
    source = files('super_review').joinpath('skills', 'super-review')
    return {name: source.joinpath(*name.split('/')).read_bytes()
            for name in ('SKILL.md', 'agents/openai.yaml')}


def _needs_install(destination: Path, contents: dict[str, bytes], force: bool) -> bool:
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError(f'Skill destination must be a directory, not a file or symlink: {destination}')
    if destination.exists():
        identical = all((destination / name).is_file()
                        and not (destination / name).is_symlink()
                        and (destination / name).read_bytes() == content
                        for name, content in contents.items())
        if identical:
            return False
        if not force:
            raise ValueError(f'Skill already exists at {destination}; use --force to back it up and replace it')
    return True


def install_skills(harnesses: list[str], project: Path | None = None,
                   force: bool = False) -> list[tuple[Path, Path | None]]:
    if not harnesses or any(h not in HARNESS_NAMES for h in harnesses):
        raise ValueError('Select harnesses from: ' + ', '.join(HARNESS_NAMES))
    root = (project if project is not None else Path.home()).expanduser().absolute()
    destinations = []
    if any(h in harnesses for h in ('codex', 'cursor', 'opencode')):
        destinations.append(root / '.agents' / 'skills' / 'super-review')
    if 'claude_code' in harnesses:
        destinations.append(root / '.claude' / 'skills' / 'super-review')
    contents = _contents()
    # Refuse conflicts across the whole selection before writing any destination.
    for destination in destinations:
        _needs_install(destination, contents, force)
    return [_install_skill(destination, contents, force) for destination in destinations]


def install_codex_skill(destination: Path, force: bool = False) -> tuple[Path, Path | None]:
    """Preserve the original command's explicit destination contract."""
    return _install_skill(destination.expanduser().absolute(), _contents(), force)


def _install_skill(destination: Path, contents: dict[str, bytes],
                   force: bool) -> tuple[Path, Path | None]:
    if not _needs_install(destination, contents, force):
        return destination, None
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.super-review-install-', dir=destination.parent))
    backup = None
    try:
        for name, content in contents.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if destination.exists():
            # Keep old SKILL.md files outside the skills root, not just renamed
            # within it: discovery can recurse through backup directories too.
            backup_root = destination.parent.parent / '.super-review-skill-backups'
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / (destination.name + '-' + uuid.uuid4().hex)
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if backup is not None:
                backup.rename(destination)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination, backup
