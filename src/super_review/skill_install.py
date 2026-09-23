"""Install the bundled Codex entry point without overwriting user edits silently."""

from importlib.resources import files
from pathlib import Path
import shutil
import tempfile
import uuid


def install_codex_skill(destination: Path, force: bool = False) -> tuple[Path, Path | None]:
    destination = destination.expanduser().absolute()
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError(f'Skill destination must be a directory, not a file or symlink: {destination}')
    source = files('super_review').joinpath('skills', 'super-review')
    contents = {name: source.joinpath(*name.split('/')).read_bytes()
                for name in ('SKILL.md', 'agents/openai.yaml')}
    if destination.exists():
        identical = all((destination / name).is_file()
                        and not (destination / name).is_symlink()
                        and (destination / name).read_bytes() == content
                        for name, content in contents.items())
        if identical:
            return destination, None
        if not force:
            raise ValueError(f'Skill already exists at {destination}; use --force to back it up and replace it')
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
