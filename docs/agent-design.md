# Agent and skill design

Research date: 2026-09-23. Version 0.5 uses model-selected native children. These choices follow primary documentation; they are not a measured optimum for review quality.

## Models own specialist selection

Each top-level review session is a parent model with a catalog of native specialist definitions. It inspects the change, selects all applicable specialists, assigns scoped questions, waits for the children and validates their findings. It may skip irrelevant roles, use multiple children of one role, or use no children for a trivial change. A delegation summary records selections, skipped roles and failed or blocked work. Those records are model claims, not independently measured child telemetry.

Python does not launch specialist sessions. It pins revisions, launches top-level harness sessions, supplies allowed peer reports, enforces cross-harness critique/revision/synthesis barriers and saves reports. The top-level graph is reproducible; child scheduling is intentionally adaptive. Four peers require 21 top-level sessions, plus however many native children their parents select.

Definitions are generated from `prompts.py`, selected `run.reviewers`, custom reviewer prompts and role model/effort settings. The package installs no permanent reviewer agent files. Each attempt saves its generated definitions and prompts in its logs.

## Native definitions and delegation

| Harness | Runtime definition | Parent and child controls |
| --- | --- | --- |
| Codex | External role TOML files registered using `agents.<name>.config_file` and description overrides; `agents.enabled=true`. | The parent runs with `--sandbox read-only`, inherited by children. Roles carry developer instructions and configured model/effort. External registration avoids depending on project agent discovery or trust. |
| Claude Code | Session-local `--agents` JSON defines the parent and named children. | Parent has Read/Grep/Glob and `Agent(named-child-allowlist)`. Children have Read/Grep/Glob, plan permission mode, and optional model/effort. Children receive no Agent tool. |
| Cursor | Temporary `.cursor/agents/*.md` definitions with `readonly: true` and configured model. | Parent uses default Agent mode, with project permissions allowing reads and denying writes, shell, MCP and web fetch. Ask mode does not guarantee native delegation. No automatic trust or force flag is supplied. |
| OpenCode | Inline configuration defines a primary parent and named `mode: subagent` children. | Parent task permissions allow only catalog children. Children deny further task delegation and use read-only permissions. Model and variant come from the role settings. |

Sources: [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference), [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Cursor subagents](https://cursor.com/docs/subagents), [Cursor CLI permissions](https://cursor.com/docs/cli/reference/permissions), [OpenCode agents](https://opencode.ai/docs/agents/), and [OpenCode schema](https://opencode.ai/config.json).

Cursor effort uses explicit `effort_models` mappings. OpenCode child variants require an explicitly configured child model, as specified by its schema. Empty child settings inherit through the native harness; empty parent settings use CLI defaults. Native concurrency limits apply to children independently of `run.concurrency`, which bounds top-level CLI processes. Parents are instructed to batch useful work, not drop relevant roles to fit a limit.

Codex and Cursor children are instructed not to delegate further; this is not a claim that their role metadata enforces a depth limit. All harnesses must support the emitted native delegation configuration. Missing delegation is a coverage failure, with no fallback to Python specialist workers.

## Context and isolation

Parents receive the pinned diff, requirements and only the peer reports allowed in their phase. Every child reads `.super-review-context.md`, containing the same evidence without the parent's task or delegation instructions. Parents should pass focused scopes without seeding children with tentative findings. Children return results through native tools; they do not write reports.

The runtime reserves its prompt/context paths and, for Cursor, its permission and role files. Existing files at those paths cause a visible failure instead of being overwritten. Generated worktree inputs are removed before source cleanliness checks. Codex role files live outside the source tree. Audit copies remain in attempt logs.

Normal authentication and provider configuration are retained. Trusted host configuration can still affect execution: Claude may load CLAUDE.md and memory, and OpenCode can retain global plugins. Read-only settings do not certify isolation from arbitrary host configuration. The adapter requests OpenCode project-config exclusion, but [issue #49836](https://github.com/anomalyco/opencode/issues/49836) reports repository plugins loading despite that flag on 1.18.31. Verify enforcement in the installed release.

Reviewers must disclose unread or truncated evidence and unavailable checks. Read-only, no-shell profiles cannot necessarily recover complete base-side files from Git; the supplied diff contains changed base lines, not complete historical source. A completed provider turn does not independently establish complete review coverage.

## Evaluation limits

Automated tests validate emitted definitions, task routing, report handling, cleanup and resume. Prompt trials exercise adaptive selection and native tool delegation in the test environment. They do not establish discovery, permissions or model availability inside the four vendor CLIs; those binaries are unavailable in this environment.

Evaluate known-defect recall, false positives, coverage, latency and cost on representative changes before claiming a quality or efficiency improvement. Compare adaptive selection with fixed-role and single-reviewer baselines. Resume reruns an interrupted parent and its children; it does not checkpoint each native child independently.

## Shared skill installation

The bundled [wrapper skill](../src/super_review/skills/super-review/SKILL.md) launches the CLI from the user's controlling session in any of the four harnesses. `super-review install-skills` installs one shared copy in `~/.agents/skills/super-review` for Codex, Cursor and OpenCode, plus an identical copy in `~/.claude/skills/super-review` for Claude Code. `--project DIRECTORY` uses the corresponding project directories. The original `install-codex-skill` command remains compatible. This shares the workflow without editing harness settings or installing persistent reviewer agents.

- [Codex skills](https://learn.chatgpt.com/docs/build-skills): explicit `$super-review`; `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`.
- [Claude Code skills](https://code.claude.com/docs/en/skills): `/super-review`, with `disable-model-invocation: true`. With no argument placeholder, Claude appends the supplied text as `ARGUMENTS: ...`; the shared instructions consume that value. No dynamic shell preprocessing or permission grants are embedded.
- [Cursor skills](https://cursor.com/docs/skills): supports the shared `.agents/skills` directory and `/super-review`, with the same `disable-model-invocation` frontmatter. [Cursor's 2.4 release](https://cursor.com/changelog/2-4) documents skill support in both the editor and CLI.
- [OpenCode skills](https://opencode.ai/docs/skills/): discovers `.agents/skills`, then loads a named skill through its skill tool. Ask it to use `super-review`; a separate slash-command wrapper is unnecessary. OpenCode ignores unknown frontmatter, including the automatic-invocation restriction, so the skill body requires an explicit swarm request before executing.

Cursor and OpenCode also discover Claude-compatible directories. The all-harness installer writes identical content to both directories, avoiding divergent instructions when the same name is discovered in both locations. Harness-specific selection installs only the required directories, but cannot stop compatible harnesses from discovering shared locations. The installer protects differing copies unless `--force` is supplied and backs up whole replaced directories outside discovery roots. Re-run the all-harness installer after upgrading to keep both copies current.

The optional message becomes review guidance through `--intent` or a UTF-8 requirements file; it does not select review peers or replace the cross-harness handoff schedule. The skill selects and announces a committed range, monitors execution, and reads the combined report. Launching from Claude/Cursor/OpenCode still uses the configured review peers and Codex synthesis.

Workers receive `SUPER_REVIEW_WORKER=1`, and the CLI rejects `run`/`resume` while it is set. The skill also instructs workers to return to their assigned review. This prevents accidental recursion; an environment marker is not a security boundary against malicious code. These integrations follow documented discovery rules; live harness discovery has not been verified in this environment.
