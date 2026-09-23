import unittest

from super_review.config import default_config, settings_for, validate_config


class ConfigTests(unittest.TestCase):
    def test_specialist_inherits_model_and_overrides_effort(self):
        cfg = default_config()
        cfg['harnesses']['codex']['defaults'] = {'model': 'test-model', 'effort': 'high'}
        cfg['harnesses']['codex']['reviewers'] = {'security': {'effort': 'xhigh'}}
        validate_config(cfg)
        self.assertEqual(settings_for(cfg, 'codex', 'specialist', 'security')['model'], 'test-model')
        self.assertEqual(settings_for(cfg, 'codex', 'specialist', 'security')['effort'], 'xhigh')
        self.assertEqual(settings_for(cfg, 'codex', 'critique')['effort'], 'high')

    def test_invalid_configuration_fails_before_execution(self):
        for key, value in [('concurrency', 0), ('timeout_seconds', -1),
                           ('harnesses', []), ('harnesses', ['codex', 'codex']),
                           ('harnesses', ['unknown']), ('reviewers', ['../escape']),
                           ('concurreny', 3), ('timeout_seconds', float('inf'))]:
            with self.subTest(key=key, value=value):
                cfg = default_config()
                cfg['run'][key] = value
                with self.assertRaises(ValueError):
                    validate_config(cfg)

    def test_cursor_effort_requires_explicit_model_mapping(self):
        cfg = default_config()
        cfg['harnesses']['cursor']['defaults'] = {'model': 'chosen', 'effort': 'high'}
        with self.assertRaisesRegex(ValueError, 'effort_models'):
            validate_config(cfg)
        cfg['harnesses']['cursor']['defaults']['effort_models'] = {'high': 'chosen-high'}
        validate_config(cfg)

    def test_unknown_harness_or_specialty_settings_rejected(self):
        for field, value in [('defalts', {}), ('reviewers', {'securty': {}}),
                             ('defaults', {'effrot': 'high'})]:
            cfg = default_config()
            cfg['harnesses']['codex'][field] = value
            with self.assertRaises(ValueError):
                validate_config(cfg)


if __name__ == '__main__':
    unittest.main()
