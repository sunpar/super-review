import json
from pathlib import Path
import tempfile
import unittest

from super_review.protocol import atomic_write, publish, verify_artifact, RunLock


class ProtocolTests(unittest.TestCase):
    def test_atomic_report_identity_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'reviews' / 'report.md'
            meta = {'run_id': 'abc', 'job_id': 'codex.review', 'phase': 'review',
                    'base_sha': 'base', 'head_sha': 'head'}
            digest = publish(p, meta, '# Review\nNo findings.')
            self.assertEqual(verify_artifact(p, meta, digest), '# Review\nNo findings.')
            with self.assertRaises(ValueError):
                verify_artifact(p, {**meta, 'run_id': 'wrong'}, digest)
            p.write_text(p.read_text() + '\ntampered')
            with self.assertRaises(ValueError):
                verify_artifact(p, meta, digest)
            self.assertFalse(list(p.parent.glob('*.tmp')))

    def test_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with RunLock(root):
                with self.assertRaisesRegex(RuntimeError, 'already running'):
                    with RunLock(root):
                        pass
            with RunLock(root):
                pass

    def test_empty_report_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                publish(Path(tmp) / 'empty.md', {}, '  ')
