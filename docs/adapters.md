# Harness adapter references

The adapter interface is `invoke(harness, settings, prompt, cwd, log_dir, timeout, max_output_bytes, agents=None, context="") -> str`. Production review jobs supply the native role catalog and shared child context. The supervisor adds report metadata and publishes completed responses atomically.

See [agent and skill design](agent-design.md) for native definition formats, selection policy and primary sources. Supported flags require recent harness versions. `doctor` checks executable/version availability, not authentication or delegation capabilities. Unsupported flags fail visibly; adapters do not retry with weaker permissions.

## Runtime inputs

Codex and Claude receive the parent prompt on stdin. Cursor and OpenCode receive a short instruction to read `.super-review-prompt.md`, keeping large diffs out of argv. All children receive the location of `.super-review-context.md`, containing pinned revisions, requirements, the full diff and allowed peer reports. Runtime files are collision-checked, verified unchanged and removed before checking for unauthorized source edits. Logs preserve copies and `native-agents.json`; Codex/Cursor native definition files are preserved too.

Codex registers external role TOMLs through configuration overrides and enables native agents. Its parent sandbox is read-only. Claude uses session-local parent and child agent definitions with a named Agent allowlist. Cursor uses Agent mode plus temporary read-only project permissions and child Markdown definitions; an existing `.cursor/cli.json` is a reserved-path conflict. OpenCode uses inline primary/subagent definitions and explicit task permissions. Global authentication/provider settings remain available. Children cannot launch another CLI swarm through the wrapper: workers carry `SUPER_REVIEW_WORKER=1`.

OpenCode specialist effort requires an explicit specialist model because its agent variant applies only with an agent model. Cursor specialist effort resolves through configured model mappings. Child settings otherwise inherit from the native parent. `run.concurrency`, timeout and output limits apply to top-level sessions, including their native child work; native concurrency is controlled by the harness.

## Output handling

Codex JSONL requires completion of the latest turn after its assistant message. Claude requires a successful JSON result envelope. Cursor requires a successful terminal result with nonempty `result`; this field aggregates assistant text and may include progress. OpenCode uses text from the final step and requires a final stop reason. Tool logs are never report bodies. Explicit errors, nonzero exits, malformed/incomplete envelopes and empty responses fail the task. Raw stdout/stderr remain in attempt logs.

Provider references: [Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Cursor parameters](https://cursor.com/docs/cli/reference/parameters), [Cursor output](https://cursor.com/docs/cli/reference/output-format), [OpenCode CLI](https://opencode.ai/docs/cli/).

## Compatibility and limits

Protocol 3 prevents older fixed-specialist runs from resuming under the native-child architecture. Finish old runs with their original package version, or start a new run with 0.5. Authentication, installed CLI versions and model defaults are not frozen in the manifest.

The OpenCode adapter requests project-configuration exclusion. [Issue #49836](https://github.com/anomalyco/opencode/issues/49836) reports a loader importing repository plugins despite that flag on 1.18.31. Treat host/provider configuration and executable plugins as trusted; adapter tests establish emitted configuration, not enforcement by an unspecified vendor release.

No vendor CLI is installed in the build environment. Tests and prompt trials cannot establish live provider authentication, native role discovery or permission enforcement. Validate a small review on each installed harness before relying on its coverage.
