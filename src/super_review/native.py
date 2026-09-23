"""Native child definitions and temporary, read-only review inputs."""

from contextlib import contextmanager
import json
from pathlib import Path

from .config import settings_for
from .prompts import SPECIALTIES, agent_name, specialist_prompt


def agent_definitions(config: dict, harness: str) -> dict:
    definitions = {}
    for reviewer in config['run']['reviewers']:
        settings = settings_for(config, harness, 'specialist', reviewer)
        model, effort = settings.get('model', ''), settings.get('effort', '')
        if harness == 'cursor' and effort:
            model = settings['effort_models'][effort]
        definitions[agent_name(reviewer)] = {
            'description': SPECIALTIES[reviewer],
            'prompt': specialist_prompt(reviewer, config['reviewer_prompts'].get(reviewer, '')),
            'model': model, 'effort': effort}
    return definitions


def codex_role(name: str, definition: dict) -> str:
    fields = {'name': name, 'description': definition['description'],
              'developer_instructions': definition['prompt'], 'sandbox_mode': 'read-only'}
    if definition['model']:
        fields['model'] = definition['model']
    if definition['effort']:
        fields['model_reasoning_effort'] = definition['effort']
    return '\n'.join(f'{k} = {json.dumps(v, ensure_ascii=False)}' for k, v in fields.items()) + '\n'


def cursor_role(name: str, definition: dict) -> str:
    fields = {'name': name, 'description': definition['description'],
              'model': definition['model'] or 'inherit', 'readonly': True}
    # JSON scalar values are valid YAML and preserve quotes/newlines safely.
    return '---\n' + '\n'.join(f'{k}: {json.dumps(v)}' for k, v in fields.items()) + \
        '\n---\n\n' + definition['prompt'] + '\n'


@contextmanager
def native_workspace(harness: str, definitions: dict, cwd: Path, logs: Path,
                     prompt: str, context: str):
    """Never replace source files; retain generated role definitions in logs."""
    inputs = {cwd / '.super-review-prompt.md': prompt,
              cwd / '.super-review-context.md': context}
    if harness == 'cursor' and definitions:
        inputs[cwd / '.cursor/cli.json'] = json.dumps({'permissions': {
            'allow': ['Read(**)'],
            'deny': ['Write(**)', 'Shell(*)', 'Mcp(*:*)', 'WebFetch(*)']}})
        inputs.update({cwd / '.cursor/agents' / f'{name}.md': cursor_role(name, value)
                       for name, value in definitions.items()})
    for path in inputs:
        if path.exists() or path.is_symlink():
            raise ValueError(f'Repository uses reserved native runtime file: {path.relative_to(cwd)}')
        parent = path.parent
        while parent != cwd:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError(f'Unsafe native runtime directory: {parent.relative_to(cwd)}')
            parent = parent.parent
    native_dir = logs.resolve() / 'native'
    native_dir.mkdir(parents=True, exist_ok=True)
    (logs / 'native-agents.json').write_text(json.dumps(definitions, indent=2), encoding='utf-8')
    (logs / 'prompt.md').write_text(prompt, encoding='utf-8')
    (logs / 'context.md').write_text(context, encoding='utf-8')
    if harness == 'codex':
        for name, value in definitions.items():
            (native_dir / f'{name}.toml').write_text(codex_role(name, value), encoding='utf-8')
    elif harness == 'cursor':
        for name, value in definitions.items():
            (native_dir / f'{name}.md').write_text(cursor_role(name, value), encoding='utf-8')
    created_files, created_dirs = [], []
    try:
        for path, body in inputs.items():
            missing = []
            parent = path.parent
            while parent != cwd and not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)
            with path.open('x', encoding='utf-8') as stream:
                created_files.append(path)
                stream.write(body)
        yield native_dir
        for path, body in inputs.items():
            if path.is_symlink() or not path.is_file() or path.read_text(encoding='utf-8') != body:
                raise ValueError('Harness modified native review inputs; report was not accepted')
    finally:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
