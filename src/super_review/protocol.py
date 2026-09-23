"""Atomic report publication, integrity checks and exclusive local run locking."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value: dict) -> str:
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(path: Path, metadata: dict, body: str) -> str:
    if not body.strip():
        raise ValueError('Cannot publish an empty report')
    header = '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=True)}'
                       for key, value in metadata.items())
    content = f'---\n{header}\n---\n\n{body.strip()}\n'
    atomic_write(path, content)
    return digest_bytes(content.encode('utf-8'))


def verify_artifact(path: Path, expected: dict, digest: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing or unsafe report: {path.name}')
    raw = path.read_bytes()
    if digest_bytes(raw) != digest:
        raise ValueError(f'Report hash mismatch: {path.name}')
    try:
        preamble, header, body = raw.decode('utf-8').split('---\n', 2)
        if preamble:
            raise ValueError('Invalid preamble')
        metadata = {}
        for line in header.splitlines():
            key, value = line.split(': ', 1)
            metadata[key] = json.loads(value)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'Invalid report metadata: {path.name}') from exc
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError(f'Report identity mismatch: {path.name}')
    if not body.strip():
        raise ValueError(f'Empty report: {path.name}')
    return body.strip()


class RunLock(AbstractContextManager):
    """flock releases on process death; a leftover lock file is harmless."""

    def __init__(self, root: Path):
        self.path = root / '.lock'
        self.stream = None

    def __enter__(self):
        if os.name != 'posix':
            raise RuntimeError('Linux, macOS, or WSL is required')
        import fcntl
        self.stream = self.path.open('a+')
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.stream.close()
            raise RuntimeError('This run is already running in another process') from exc
        return self

    def __exit__(self, *args):
        self.stream.close()
