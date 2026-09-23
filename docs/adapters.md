# Harness adapter references

The adapter interface is `invoke(harness, settings, prompt, cwd, log_dir, timeout,
max_output_bytes) -> str`. A completed provider response becomes a Markdown body;
the supervisor adds metadata and publishes it atomically.

Reviewed against primary CLI documentation on 2026-09-22:

- [Codex CLI reference](https://developers.openai.com/codex/cli/reference/)
- [Codex non-interactive execution](https://developers.openai.com/codex/noninteractive/)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Cursor parameters](https://cursor.com/docs/cli/reference/parameters)
- [Cursor output formats](https://cursor.com/docs/cli/reference/output-format)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
- [OpenCode permissions](https://opencode.ai/docs/permissions/)

Codex/Claude receive the complete prompt on stdin. Cursor/OpenCode receive a short
instruction to read the local task prompt, keeping large diffs out of argv. The
prompt file exists only inside the task's disposable working tree and is removed
before checking for unauthorized edits.

Codex JSONL requires a completed turn and an assistant message. Claude requires
a successful JSON result envelope. Cursor uses its last complete assistant message
and requires a successful terminal result. OpenCode JSONL uses only text from the
last step and requires a final stop reason. Intermediate progress text is excluded.
Any explicit error, nonzero exit, malformed/incomplete
envelope or empty response fails the task. Raw stdout/stderr remain in attempt logs.

No real model calls were used to develop the initial automated test suite. Account
authentication, permission policies and provider-specific model/effort combinations
are installation-specific. Verify a small review before running a full panel.
