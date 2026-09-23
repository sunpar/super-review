import unittest

from super_review.config import default_config
from super_review.prompts import render_context, render_prompt
from super_review.runner import plan_jobs


class PromptTests(unittest.TestCase):
    def test_children_receive_shared_evidence_without_parent_delegation_task(self):
        cfg = default_config()
        manifest = {'config': cfg, 'target': {'base_sha': 'base', 'head_sha': 'head'},
                    'requirements': 'Keep the API stable.'}
        jobs = plan_jobs(cfg, 'run')
        patch = 'diff --git a/calc.py b/calc.py\n-old\n+new\n'
        context = render_context(manifest, patch, {'peer': 'Evidence from a peer.'})
        parent = render_prompt(manifest, jobs['codex.coordinator'], patch,
                               {'peer': 'Evidence from a peer.'})
        self.assertIn(patch, context)
        self.assertIn('Keep the API stable.', context)
        self.assertIn('Evidence from a peer.', context)
        self.assertIn(context, parent)
        self.assertNotIn('TASK_JSON:', context)
        self.assertIn('TASK_JSON:', parent)
