# Agent and skill design

Research date: 2026-09-23. These recommendations follow current primary documentation and the package's architecture; they are not an experimentally proven optimum.

## Keep scheduling in Python

Use one fresh CLI session for each specialist, coordinator, critique, revision and synthesis job. Python selects the job, pins its source revision, supplies its allowed reports, enforces dependency barriers and resource limits, and publishes the result. A model should inspect evidence and write its assigned review, without deciding which reviewers run or launching another review tree.

This makes the **workflow** deterministic: the same configuration produces the same job graph and input routing. Model findings remain nondeterministic. Fresh contexts also preserve independent first reviews and prevent an earlier phase's conversation from silently influencing another phase. Supplied peer reports become explicit inputs at the appropriate stage.

The ordinary `pipx` package is sufficient. It generates task instructions and runtime agent definitions; users do not need to install forty persistent agent files. Native agent and skill formats remain useful for optional integrations:

| Harness | Native custom agents | Reusable skills |
| --- | --- | --- |
| Codex | TOML in `.codex/agents/` or `~/.codex/agents/`; required `name`, `description`, `developer_instructions`; optional model, effort and sandbox settings. [Agents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | `.agents/skills/<name>/SKILL.md` in the repository, or `~/.agents/skills/<name>/SKILL.md`; YAML name/description plus instructions. [Skills](https://learn.chatgpt.com/docs/build-skills) |
| Claude Code | Markdown with YAML frontmatter in `.claude/agents/` or `~/.claude/agents/`; alternatively a session-local `--agents` JSON definition. [Agents](https://code.claude.com/docs/en/sub-agents) | `.claude/skills/<name>/SKILL.md` or `~/.claude/skills/<name>/SKILL.md`. [Skills](https://code.claude.com/docs/en/skills) |
| Cursor | Markdown with YAML frontmatter in `.cursor/agents/` or `~/.cursor/agents/`; supports model selection and `readonly: true`. [Agents](https://cursor.com/docs/subagents) | `.cursor/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md`, with corresponding user directories. [Skills](https://cursor.com/docs/skills) |
| OpenCode | Markdown with YAML frontmatter in `.opencode/agents/` or `~/.config/opencode/agents/`, or JSON configuration under `agent.<name>`. [Agents](https://opencode.ai/docs/agents/) | `.opencode/skills/<name>/SKILL.md` or `~/.config/opencode/skills/<name>/SKILL.md`; also discovers Claude-compatible and `.agents/skills` directories. [Skills](https://opencode.ai/docs/skills/) |

These are principal authoring locations, not exhaustive discovery rules. A skill supplies reusable guidance; it does not by itself create an independent session or enforce the supervisor's schedule.

## CLI implementation choices

| Harness | Choice for each job |
| --- | --- |
| Codex | `-a never exec --sandbox read-only --json --ephemeral`, prompt on stdin. Explicit overrides disable web search, lifecycle hooks and native multi-agent tools. Keep normal authentication/provider configuration. Select model with `--model`, effort with `model_reasoning_effort`. |
| Claude Code | Noninteractive `-p --output-format json`, with a session-local reviewer defined by `--agents` and selected by `--agent`. Its prompt carries the common contract; expose only Read/Grep/Glob. Keep user settings, disable slash commands and hooks, use strict empty MCP configuration and no session persistence. Select `--model` and supported `--effort`. |
| Cursor | `--print --mode ask --output-format stream-json`, with an in-worktree prompt file. Pass the model ID through `--model`; effort uses explicitly configured model mappings rather than inventing a universal effort flag. Validate the terminal success envelope and take its nonempty `result`. |
| OpenCode | `run --format json --agent super-review`, with an inline configured **primary** agent carrying the common prompt and read-only permissions. Request project-config exclusion; disable sharing, snapshots and automatic updates. Retain global authentication/providers/plugins. Use `--model` and provider-supported `--variant`. |

See the official CLI references for [Codex](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [Claude Code](https://code.claude.com/docs/en/cli-reference), [Cursor](https://cursor.com/docs/cli/reference/parameters) and [OpenCode](https://opencode.ai/docs/cli/). Supported flags and model identifiers depend on the installed release and account.

Cursor's [terminal result](https://cursor.com/docs/cli/reference/output-format) aggregates assistant text, which can include progress. It is not guaranteed to contain only the last message. Selecting the last assistant segment instead can discard report content. The review prompt requests report-only text.

Avoid unconditionally discarding global configuration to obtain a cleaner session: that can break configured providers and login flows. The retained configuration is trusted. In particular, Claude's main `--agent` session can still receive CLAUDE.md and memory; OpenCode can retain global plugins. Read-only controls do not make arbitrary host configuration or repository content harmless.

There is also a known project-plugin limitation: [OpenCode issue #49836](https://github.com/anomalyco/opencode/issues/49836), open at this review, reproduces repository plugin execution on 1.18.31 despite `OPENCODE_DISABLE_PROJECT_CONFIG`. The legacy loader honors the flag but newer discovery does not consistently do so. The adapter requests exclusion; it cannot certify enforcement. Verify the upstream fix and installed version, and treat repository plugins as trusted executable code.

## Contracts, skills and coverage

Supply essential instructions directly: specialty, pinned base/head, complete diff, requirements, report identity, finding criteria, severity/confidence rubric and allowed peer reports. Keep reusable supplementary references short and load them only when relevant. Discovery-based skill activation should not decide whether a required review step happens.

The bundled [Codex wrapper skill](../src/super_review/skills/super-review/SKILL.md) invokes the installed CLI once from the user's controlling session. Install it with `super-review install-codex-skill`. Its `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`, following the [Codex skill configuration](https://learn.chatgpt.com/docs/build-skills). The optional invocation message becomes review guidance through `--intent` or a UTF-8 requirements file; it does not replace Python scheduling or create native subagents. The skill selects and announces a committed range, monitors execution, and reads the combined report.

Workers receive `SUPER_REVIEW_WORKER=1`, and the CLI rejects `run`/`resume` while that marker is set. The skill also instructs workers to return to their assigned review. This prevents accidental recursion; an environment marker is not a security boundary against malicious code. Installation is idempotent, protects differing user edits, and backs up replaced skills outside discovery directories.

Stage any required prompt references within the permitted worktree. Claude/OpenCode's no-shell reviewers cannot run `git show` to inspect full base-side source: the diff and HEAD checkout may not establish historical behavior. Materialize needed base files before requiring that comparison, or record the missing evidence as a limitation. Do not broaden permissions merely to suppress the limitation.

Require coverage and limitations to identify unreadable/truncated material and checks not performed. A completed CLI turn does not prove complete inspection, and “no actionable findings” is not assurance about uninspected code. A failed tool call may recover, so do not treat every tool failure as a failed review.

## Evaluate before claiming improvement

Measure known-defect recall, false positives, evidence accuracy, coverage, latency and token use across representative repositories. Compare the fixed specialist suite with simpler baselines, and assess critique/revision gains separately. Test supported CLI releases with real-provider fixtures before claiming compatibility or quality.

Stable common context before task-specific content may help caching, but [OpenAI's caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching) requires matching rendered prefixes and eligible cache boundaries. Worktree paths, system instructions and model settings can prevent reuse. No cache saving or review-quality improvement is guaranteed by this layout.
