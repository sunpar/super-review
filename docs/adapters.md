# Harness adapter references

The adapter interface is `invoke(harness, settings, prompt, cwd, log_dir, timeout,
max_output_bytes) -> str`. A completed provider response becomes a Markdown body;
the supervisor adds metadata and publishes it atomically.

Reviewed against primary CLI documentation on 2026-09-23:

- [Codex CLI reference](https://developers.openai.com/codex/cli/reference/)
- [Codex non-interactive execution](https://developers.openai.com/codex/noninteractive/)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Cursor parameters](https://cursor.com/docs/cli/reference/parameters)
- [Cursor output formats](https://cursor.com/docs/cli/reference/output-format)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
- [OpenCode permissions](https://opencode.ai/docs/permissions/)

See [agent and skill design](agent-design.md) for native agent definitions, skill
authoring locations, configuration boundaries and the reasoning behind the profiles.
The profiles retain ordinary user/provider authentication; they require recent CLIs
supporting the emitted flags. Unsupported flags fail visibly, and the supervisor
does not retry using weaker permissions. `doctor` is a version/executable check,
not a capability or authentication certification.

Codex/Claude receive the complete prompt on stdin. Cursor/OpenCode receive a short
instruction to read the local task prompt, keeping large diffs out of argv. The
prompt file exists only inside the task's disposable working tree and is removed
before checking for unauthorized edits.

Codex JSONL requires completion of the latest turn after its assistant message;
an earlier completed turn cannot validate a later interrupted turn. Claude requires
a successful JSON result envelope. Cursor requires a successful terminal result
with nonempty `result` text, as specified by its protocol. That field aggregates
assistant text and may contain progress; selecting only the last assistant segment
can silently discard report content. OpenCode JSONL uses only text from the last
step and requires a final stop reason. Tool logs are never used as report bodies.
Any explicit error, nonzero exit, malformed/incomplete
envelope or empty response fails the task. Raw stdout/stderr remain in attempt logs.

Claude gets an explicit session-local native agent and the same common contract
as the other harnesses. Only Read/Grep/Glob are available; project/local settings,
slash commands, hooks and MCP servers are excluded. CLAUDE.md and memory can still
load. OpenCode's inline primary agent sets its system prompt, tool permissions and
`disable: false`; project-configuration exclusion is requested and automatic sharing is
explicitly disabled in configuration and environment. Global authentication/plugins
remain trusted. Snapshots and automatic updates are disabled for these read-only
jobs. Codex sessions are ephemeral, with web search, hooks and nested agents disabled;
its normal model/provider configuration remains available.

OpenCode's legacy config loader honors `OPENCODE_DISABLE_PROJECT_CONFIG`, but
[issue #49836](https://github.com/anomalyco/opencode/issues/49836) reproduces a newer
loader importing repository plugins despite that flag on 1.18.31. This issue was
open on 2026-09-23. Do not treat the flag as verified isolation from project startup
code; use trusted repositories and verify the upstream fix against your installation.
The environment override regression test checks what this adapter sends, not whether
an unspecified OpenCode release correctly enforces it.

Protocol 2 separates these profiles and prompts from version 0.1 runs. Resume old
runs with the original package version, or start a new run with 0.2. Authentication,
installed harness versions and model defaults are not frozen by the
manifest; use explicit model choices and keep harness installations stable during
a run if reproducibility matters.

No real model calls were used to develop the initial automated test suite. Account
authentication, permission policies and provider-specific model/effort combinations
are installation-specific. Verify a small review before running a full panel.
