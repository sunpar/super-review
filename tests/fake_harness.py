"""A deterministic external CLI fixture, never shipped as a production adapter."""
import json
import os
from pathlib import Path
import sys
import time

harness, events_file, failure = sys.argv[1:4]
prompt = sys.stdin.read() if harness in ('codex', 'claude_code') else Path('.super-review-prompt.md').read_text()
marker = next(line for line in prompt.splitlines() if line.startswith('TASK_JSON: '))
task = json.loads(marker.removeprefix('TASK_JSON: '))
if 'SUPER_REVIEW_TEST_EXPECT_INTENT' in os.environ:
    assert os.environ['SUPER_REVIEW_TEST_EXPECT_INTENT'] in prompt


def record(event):
    data = {'event': event, 'job': task['id'], 'phase': task['phase'],
            'harness': harness, 'time': time.monotonic(), 'cwd': str(Path.cwd()),
            'worker': os.environ.get('SUPER_REVIEW_WORKER')}
    with open(events_file, 'a') as output:
        output.write(json.dumps(data) + '\n')


record('start')
if failure == task['id'] and not Path(events_file + '.failed').exists():
    Path(events_file + '.failed').touch()
    record('fail')
    print('fake API failure', file=sys.stderr)
    sys.exit(7)
if failure == 'slow-opencode' and harness == 'opencode' and task['phase'] == 'specialist':
    time.sleep(.6)
else:
    time.sleep(.01)
if failure == 'modify-source':
    Path('calc.py').write_text('bad change')
if task['phase'] == 'synthesis':
    # The final job must not see critique or initial report bodies.
    assert 'FAKE_BODY:critique' not in prompt
    assert 'FAKE_BODY:coordinator' not in prompt
    assert prompt.count('FAKE_BODY:revision') == len(task['dependencies'])
body = f'# Review\nFAKE_BODY:{task["phase"]}\n\nNo actionable findings.'
record('end')
if harness == 'codex':
    print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': body}}))
    print(json.dumps({'type': 'turn.completed', 'usage': {}}))
elif harness in ('claude_code', 'cursor'):
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': body}))
else:
    print(json.dumps({'type': 'text', 'part': {'type': 'text', 'text': body}}))
    print(json.dumps({'type': 'step_finish', 'part': {'reason': 'stop'}}))
