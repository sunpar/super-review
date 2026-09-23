# Super Review

Independent specialist code reviews across **Codex, Claude Code, Cursor CLI, and
OpenCode**, followed by peer critiques, self-revision, and one combined Codex review.

Every specialist and phase gets a fresh CLI process and independently configurable
model/effort. Python schedules jobs and waits for files; models never spend tokens
polling directories. The supervisor stores review reports locally.

## Install

Requires **Python 3.11+, Git, and Linux/macOS/WSL**. Install and authenticate the
harnesses you want to use; **Codex is always required for final synthesis**.

```bash
pipx install 'git+https://github.com/sunpar/super-review.git'
# Or:
uv tool install 'git+https://github.com/sunpar/super-review.git'
```

From a downloaded or cloned source tree:

```bash
pipx install .
# Or use a virtual environment:
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

No runtime Python dependencies. Authentication and model billing use each installed
harness's existing configuration. This package does not install harnesses or manage
provider credentials.

Upgrade an existing installation with `pipx upgrade super-review-swarm` (or
`uv tool upgrade super-review-swarm`). Versions 0.2–0.4 use review protocol 2: finish
0.1 runs with 0.1, or start a new run after upgrading. Old reports remain readable,
but mixing earlier prompts and adapter policies with new jobs is rejected.

## First review

In the Git repository you want to review:

```bash
super-review init
# Edit super-review.toml to select harnesses, models and effort.
super-review doctor

# Inspect all jobs and CLI arguments without calling a model:
super-review run --base origin/main --head HEAD --dry-run

super-review run --base origin/main --head HEAD \
  --intent 'Explain the intended behavior of this change'
```

The generated configuration initially enables **Codex only** and all ten specialists.
Enable every peer with:

```bash
super-review run --base origin/main --head HEAD \
  --harnesses codex,claude_code,cursor,opencode \
  --requirements docs/feature-spec.md \
  --output .reviews
```

Four peers and ten specialties produce **61 model calls** before retries: 40
specialists, 4 initial reviews, 12 directed critiques, 4 revisions, and 1 synthesis.
Concurrency defaults to 4. For a smaller first run:

```bash
super-review run --base HEAD~1 --reviewers correctness,security,testing --concurrency 2
```

Only committed changes are reviewed. The base defaults to the merge-base of `--base`
and `--head`; use `--exact-base` for an exact two-commit comparison. Nothing is fetched
automatically, so update your remote refs yourself. Dirty/untracked local edits are
excluded. Supply `--config /path/to/config.toml` to reuse settings across projects.

<a id="run-from-codex"></a>
## Run from your coding harness

After installing or upgrading the package, install its skills on each machine:

```bash
super-review install-skills
# Updating an existing 0.3 skill? Preserve a backup and replace it:
super-review install-skills --force
```

The default installs for **all four harnesses**, using two locations:

| Harness | User installation | Invocation inside the harness |
| --- | --- | --- |
| Codex | `~/.agents/skills/super-review` (shared) | `$super-review` |
| Cursor CLI | Same shared installation | `/super-review` |
| OpenCode | Same shared installation | `Use the super-review skill` |
| Claude Code | `~/.claude/skills/super-review` (same bundled content) | `/super-review` |

Append optional guidance to any invocation, for example:

```text
$super-review Focus on SQL join correctness and race conditions
/super-review Focus on SQL join correctness and race conditions
Use the super-review skill. Focus on SQL join correctness and race conditions.
```

Use the appropriate line for your harness. OpenCode loads the named skill through
its native skill tool; this installer does not add a custom OpenCode slash command.
Codex, Claude Code and Cursor have metadata disabling automatic invocation.
OpenCode ignores that metadata, so the shared instructions require an explicit
user request before executing the swarm.

The optional message goes to every review phase as guidance. The skill uses your
repository's `super-review.toml`, including its enabled harnesses and model settings;
without a config it uses Codex and all ten specialists. The harness launching the
skill does **not** change the review peers; Codex is still required for synthesis.
It selects and announces a committed comparison against the local default branch,
falling back to the last commit when there are no branch changes. You can explicitly
specify the base/head in your request. Dirty/untracked changes are excluded, and a
focus message does not restrict which paths enter the diff. The skill waits for
the CLI and summarizes the combined report.

To select installation locations or install in one project:

```bash
super-review install-skills --harnesses claude_code,cursor,opencode
super-review install-skills --project .
```

Project installations use `.agents/skills/super-review` and
`.claude/skills/super-review` below the chosen directory. `--harnesses` selects
installation targets, not review peers. Shared directories may also be discovered
by other compatible harnesses. Cursor/OpenCode can discover the Claude-compatible
copy too; both copies contain the same workflow. No extra `.cursor` or `.opencode`
copy is created. Keep the two copies in sync with the default all-harness command.

An identical installation is a no-op. A differing copy is protected unless you use
`--force`; the entire previous directory is backed up outside the skills directory
and its location is printed. All selected destinations are checked for conflicts
before writing. Each skill is staged as a complete directory; an I/O failure later
in a multi-directory installation may leave earlier directories updated. Rerun after
resolving the error. Run the installer again after package upgrades.

The existing `super-review install-codex-skill` command still works and updates the
shared installation only. Its `--path` option installs the same bundle at an exact
custom skill directory, including a nonstandard harness configuration location.

The controlling harness must be able to execute `super-review` and the configured,
authenticated harnesses in its environment. Use a mode that permits shell execution;
a hosted session needs the tools available there, too. Normal host execution and
approval rules still apply. The supervisor marks worker processes with
`SUPER_REVIEW_WORKER=1`; the CLI refuses nested `run`/`resume` calls from those workers
to prevent accidental recursive swarms.

See the [official discovery and invocation references](docs/agent-design.md#shared-skill-installation).

## Workflow

1. Pin the base/head commits and save the full diff and configuration.
2. Run the same specialist suite independently through every enabled harness.
3. Each harness assembles its specialists into one initial Markdown review.
4. As peer reviews become available, harnesses critique one another. A harness
   starts critiques only after finishing its own independent review.
5. After **all directed critiques** complete, each harness revises its own review
   using every critique addressed to it.
6. Codex reads **only the final peer reviews**, plus the pinned code context, and
   produces one deduplicated review. Findings are judged on evidence, never votes.

The ten specialties are correctness, edge cases, security, concurrency, performance,
API contracts, data integrity/SQL/numerics, testing, architecture, and operations.
The package launches specialist agents as separate CLI sessions; it does not ask
a parent model to decide whether to create native subagents.

## Model and effort configuration

Settings inherit from `harnesses.<name>.defaults`. A reviewer override applies to
that specialist; `coordinator`, `critique`, and `revision` independently override
their phases. `[synthesis]` overrides Codex defaults for the final report.

```toml
[harnesses.codex.defaults]
model = "your-model-id"
effort = "high"

[harnesses.codex.reviewers.security]
effort = "xhigh"

[harnesses.claude_code.defaults]
model = "sonnet"
effort = "high"

[harnesses.claude_code.reviewers.correctness]
model = "opus"

[harnesses.claude_code.critique]
model = "opus"

[synthesis]
model = "your-codex-model-id"
effort = "high"
```

These are configuration examples; choose identifiers and effort levels supported
by your account. Empty strings explicitly inherit the CLI's own defaults. Omit a
phase key to inherit the harness defaults. No effort value is silently translated
to a supposedly equivalent level on another provider.

| Harness | Model | Effort | Review restriction |
|---|---|---|---|
| Codex | `--model` | `model_reasoning_effort` | read-only sandbox, approvals never; ephemeral session, web search/hooks/nested agents disabled |
| Claude Code | `--model` | `--effort` | explicit native reviewer; Read/Grep/Glob only, plan mode, hooks/skills disabled, empty MCP config, user settings only |
| Cursor | `--model` | Explicit model-ID mapping | Ask mode |
| OpenCode | `--model provider/model` | `--variant` | explicit primary reviewer; read/glob/grep/list allowed, automatic sharing disabled, project-config exclusion requested |

These profiles use current documented CLI capabilities. Use recent harness
releases; unsupported flags fail the task rather than silently weakening it.
See the [agent and skill design research](docs/agent-design.md) for choices and sources.

The supervisor resolves executable paths before entering job worktrees, preserving
symlinks such as virtual-environment Python. If `command` includes wrapper scripts
or other path arguments, use absolute paths for those arguments. Claude project
settings are excluded and OpenCode is asked to exclude project configuration; keep provider settings
in user/global configuration or set models explicitly in `super-review.toml`.

**OpenCode compatibility:** [upstream issue #49836](https://github.com/anomalyco/opencode/issues/49836)
reports that 1.18.31 still loads repository `.opencode` plugins despite its exclusion
flag. Treat repository plugins as executable trusted code; this setting is not an
isolation guarantee. The issue was open at the 2026-09-23 review. Check the upstream
fix and your installed version before relying on that exclusion.

Cursor has no universal effort flag. Run `agent models` and map the requested effort
to an exact available model ID:

```toml
[harnesses.cursor.defaults]
effort = "high"
[harnesses.cursor.defaults.effort_models]
high = "exact-model-id-from-agent-models"
```

If your Cursor executable is `cursor-agent`, set
`[harnesses.cursor] command = ["cursor-agent"]` using normal TOML table syntax.
OpenCode users can inspect their available models with `opencode models`.

## Output and resume

By default, runs are saved in `~/.cache/super-review/runs` (honoring `XDG_CACHE_HOME`).
`--output .reviews` puts them in your chosen repository; add `.reviews/` to its ignore
file. Each run uses one shared UTC timestamp and random suffix.

```text
<run-id>/
  manifest.json
  diff.patch
  specialists/<harness>_<specialty>_<run-id>.md
  reviews/<harness>_<run-id>.md
  critiques/<author>_critique_<target>_<run-id>.md
  final/<harness>_final_<run-id>.md
  combined_review_<run-id>.md
  logs/<job-id>/<attempt>/
  repository.git/
```

Reports have supervisor-generated metadata containing the run, commits, phase,
author, requested model/effort and timestamp. Default models are labeled as CLI
defaults; the supervisor does not claim to know the provider's resolved model.
The manifest records exact expected filenames, checksums, dependencies and status.

```bash
super-review status /path/to/run-id
super-review resume /path/to/run-id
```

Completed reports are verified and reused. Failed/interrupted jobs run again in
fresh contexts; they do not resume a provider's previous conversation. Altered
reports or inputs stop resume instead of silently mixing results. Start a new run
to change models, requirements or the Git target. An exclusive OS lock prevents
two supervisors from advancing the same run. If the host dies after publication
but before the manifest update, that job may be repeated.

Individual tasks default to 15 minutes; each invocation of run/resume has a
two-hour limit. Configure both in TOML. Output capture is bounded; failures retain
logs. Timeouts and Ctrl-C terminate the harness process group. `SIGKILL`/host crashes
can leave a disposable worktree behind; remove the entire run directory when you
no longer need its records, after ensuring its processes have stopped.

## Scope and safety

The source checkout is never a harness working directory. A private local Git
copy has no remotes, and each task gets its own detached worktree. Reports are
published only after checking that the task did not change its working tree.
Supervisor Git commands disable hooks and never initialize submodules or fetch.

Read-only harness controls are **not an operating-system security boundary**.
Run against trusted repositories and trusted harness configuration. Harnesses run
as your user, may load global/project instructions or integrations, and send code
to their configured model providers. Use a container/VM with suitable credentials
and network policy for hostile repositories. This tool does not run tests or
reproducers, apply fixes, post PR comments, or upload reports automatically.

Changed submodules are rejected; LFS objects are not downloaded. Non-UTF-8 content
is represented through Git's diff output and may not be fully reviewable. Large
diffs/reports can exceed model context limits; narrow the committed change instead
of treating an incomplete review as evidence of coverage. Output completion checks
validate the harness protocol, not the truth or completeness of model findings.

CLI interfaces and account model access can change. `doctor` checks executables and
versions, not authentication or every provider setting. If a CLI reports a missing
flag, update it or consult [adapter references](docs/adapters.md). Cursor may require
you to establish trust for a newly created workspace; this package does not force
trust or bypass its permission policy.

Reviewers are asked to report `Review status: COMPLETE` or `INCOMPLETE`, their
inspected scope, and unread or truncated evidence. These are model claims, not
supervisor-verified coverage. In particular, Claude/OpenCode have no shell tool:
they see HEAD and the full diff, but cannot use Git to recover complete historical
files. They must disclose missing base context when it matters. Cursor's canonical
terminal result includes all assistant text, so progress prose can appear in a
report; tool logs are excluded.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pip install build
python -m build
```

Tests use temporary Git repositories and real subprocess fixture executables to
cover orchestration, adapter envelopes, barriers, concurrency, timeout, resume,
tamper detection and CLI behavior. They do not make paid model calls. Live model
execution must be checked with installed and authenticated CLI versions.

See [design](docs/design.md) and [implementation plan](docs/implementation-plan.md).
The initial release implements the complete review/critique/revision/synthesis
workflow; automatic fixing and executable reproducer agents are outside its scope.

MIT licensed.
