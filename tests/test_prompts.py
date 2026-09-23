import unittest

from super_review.config import default_config
from super_review.prompts import render_prompt
from super_review.runner import plan_jobs


class PromptTests(unittest.TestCase):
    def test_specialists_share_the_complete_diff_prefix(self):
        cfg = default_config()
        manifest = {'config': cfg, 'target': {'base_sha': 'base', 'head_sha': 'head'},
                    'requirements': 'Keep the API stable.'}
        jobs = plan_jobs(cfg, 'run')
        patch = 'diff --git a/calc.py b/calc.py\n-old\n+new\n'
        left = render_prompt(manifest, jobs['codex.specialist.correctness'], patch, {})
        right = render_prompt(manifest, jobs['codex.specialist.security'], patch, {})
        # Early job identity used to invalidate the entire large shared diff prefix.
        prefix_end = left.index(patch) + len(patch)
        self.assertEqual(left[:prefix_end], right[:prefix_end])
        self.assertNotEqual(left[prefix_end:], right[prefix_end:])
