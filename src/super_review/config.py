"""Strict configuration and predictable setting inheritance."""

from __future__ import annotations

import copy
import math
from pathlib import Path
import tomllib

HARNESS_COMMANDS = {'codex': ['codex'], 'claude_code': ['claude'],
                    'cursor': ['agent'], 'opencode': ['opencode']}
REVIEWERS = ('correctness', 'edge_cases', 'security', 'concurrency', 'performance',
             'api_contracts', 'data_integrity', 'testing', 'architecture', 'operations')
PHASES = ('coordinator', 'critique', 'revision')
SETTING_KEYS = {'model', 'effort', 'effort_models'}


def default_config() -> dict:
    return {'version': 1,
            'run': {'harnesses': ['codex'], 'reviewers': list(REVIEWERS),
                    'concurrency': 4, 'timeout_seconds': 900,
                    'total_timeout_seconds': 7200, 'max_output_bytes': 8_388_608,
                    'output_root': ''},
            'harnesses': {name: {'command': cmd.copy(), 'defaults': {}, 'reviewers': {}}
                          for name, cmd in HARNESS_COMMANDS.items()},
            'synthesis': {}, 'reviewer_prompts': {}}


def _keys(value: dict, allowed: set, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a table')
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f'{label}: unknown keys: {sorted(unknown)}')


def _settings(value: dict, label: str) -> None:
    _keys(value, SETTING_KEYS, label)
    for key in ('model', 'effort'):
        if key in value and (not isinstance(value[key], str) or '\x00' in value[key]):
            raise ValueError(f'{label}.{key} must be a string without NUL')
    if 'effort_models' in value:
        mapping = value['effort_models']
        if not isinstance(mapping, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) or not v or '\x00' in v
                for k, v in mapping.items()):
            raise ValueError(f'{label}.effort_models must map efforts to model identifiers')


def settings_for(config: dict, harness: str, phase: str, reviewer: str | None = None) -> dict:
    definition = config['harnesses'][harness]
    result = copy.deepcopy(definition.get('defaults', {}))
    override = (definition.get('reviewers', {}).get(reviewer, {}) if phase == 'specialist'
                else config.get('synthesis', {}) if phase == 'synthesis'
                else definition.get(phase, {}))
    result.update(copy.deepcopy(override))
    result['command'] = definition['command'].copy()
    return result


def validate_config(config: dict) -> dict:
    _keys(config, {'version', 'run', 'harnesses', 'synthesis', 'reviewer_prompts'}, 'config')
    if type(config.get('version')) is not int or config['version'] != 1:
        raise ValueError('version must be 1')
    run = config.get('run', {})
    _keys(run, set(default_config()['run']), 'run')
    for key in ('concurrency', 'timeout_seconds', 'total_timeout_seconds', 'max_output_bytes'):
        value = run.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'run.{key} must be positive and finite')
    for key in ('concurrency', 'max_output_bytes'):
        if type(run[key]) is not int:
            raise ValueError(f'run.{key} must be an integer')
    for key, allowed in [('harnesses', HARNESS_COMMANDS), ('reviewers', REVIEWERS)]:
        values = run.get(key)
        if not isinstance(values, list) or not values or any(
                not isinstance(x, str) or x not in allowed for x in values):
            raise ValueError(f'run.{key} must be a nonempty list from {list(allowed)}')
        if len(set(values)) != len(values):
            raise ValueError(f'run.{key} must not contain duplicates')
    if not isinstance(run.get('output_root'), str):
        raise ValueError('run.output_root must be a string')
    _keys(config.get('harnesses', {}), set(HARNESS_COMMANDS), 'harnesses')
    for name in HARNESS_COMMANDS:
        h = config['harnesses'].get(name)
        _keys(h, {'command', 'defaults', 'reviewers', *PHASES}, f'harnesses.{name}')
        command = h.get('command')
        if not isinstance(command, list) or not command or any(
                not isinstance(x, str) or not x or '\x00' in x for x in command):
            raise ValueError(f'{name}.command must be a nonempty argument array')
        for phase in ('defaults', *PHASES):
            _settings(h.get(phase, {}), f'{name}.{phase}')
        _keys(h.get('reviewers', {}), set(REVIEWERS), f'{name}.reviewers')
        for specialty, settings in h.get('reviewers', {}).items():
            _settings(settings, f'{name}.reviewers.{specialty}')
    _settings(config.get('synthesis', {}), 'synthesis')
    _keys(config.get('reviewer_prompts', {}), set(REVIEWERS), 'reviewer_prompts')
    if any(not isinstance(x, str) for x in config.get('reviewer_prompts', {}).values()):
        raise ValueError('reviewer_prompts must contain strings')
    for phase, reviewer in [('specialist', r) for r in REVIEWERS] + [(p, None) for p in PHASES]:
        settings = settings_for(config, 'cursor', phase, reviewer)
        effort = settings.get('effort')
        if effort and effort not in settings.get('effort_models', {}):
            raise ValueError('Cursor effort requires an explicit effort_models mapping to CLI model IDs')
    return config


def load_config(path: Path | None) -> dict:
    config = default_config()
    if path is not None:
        with path.open('rb') as stream:
            supplied = tomllib.load(stream)
        _keys(supplied, set(config), 'config')
        for section, value in supplied.items():
            if section == 'harnesses':
                _keys(value, set(HARNESS_COMMANDS), 'harnesses')
                for name, definition in value.items():
                    _keys(definition, {'command', 'defaults', 'reviewers', *PHASES}, name)
                    config[section][name].update(definition)
            elif isinstance(config[section], dict) and isinstance(value, dict):
                config[section].update(value)
            else:
                config[section] = value
    return validate_config(config)
