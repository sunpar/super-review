# Guide for agents maintaining Super Review

This file applies to the entire repository. It describes how to maintain the project;
it is not the read-only review contract supplied to models by the product. Follow the
user's current task and preserve unrelated changes. Keep this guide current when
architecture, packaging, commands or compatibility rules change.

## Project identity and distribution

- Public repository: https://github.com/sunpar/super-review; distribution branch: `main`.
- Python distribution: `super-review-swarm`; import package: `super_review`;
  console command: `super-review` (`super_review.cli:main`).
- Python 3.11+; Linux, macOS or WSL. Native Windows is unsupported because locking
  and process cancellation use POSIX behavior.
- Standard-library runtime only. Build backend is setuptools (`setuptools>=77`).
  Do not add runtime dependencies casually.
- Users install directly from GitHub. There is no PyPI publishing or automated
  GitHub Release workflow configured here. Do not describe a main-branch update
  as a PyPI release or a release tag unless those actions actually happened.
- The package does not install vendor harnesses, manage credentials or provide
  model access. Users install/authenticate their own CLIs; existing provider
  accounts and billing apply. Codex is required for synthesis even when it is
  not selected as a review peer.

```bash
pipx install 'git+https://github.com/sunpar/super-review.git'
# Alternative:
uv tool install 'git+https://github.com/sunpar/super-review.git'

# Upgrade an existing installation:
pipx upgrade super-review-swarm
# Or: uv tool upgrade super-review-swarm
super-review install-skills --force
```

`--force` backs up differing installed skills. Package upgrades do not automatically
refresh copies previously installed in users' skill directories.

## Architecture: preserve native model-owned delegation

The user explicitly requested that parent models choose and spawn native child
agents. Do not reintroduce a fixed Python specialist-worker schedule.

Python pins source revisions, starts top-level CLI sessions, routes peer reports,
enforces cross-harness barriers and persists/resumes runs. Each model parent owns
specialist selection, scope, spawning, waiting and validation. `run.reviewers` is
an available role catalog, not a mandatory execution list. Parents can skip
irrelevant roles, instantiate a role more than once, request follow-ups or use zero
children for a trivial change. They must explain selection and material gaps.

For N review peers the top-level graph has N initial reviews, N*(N-1) directed
critiques, N revised reviews and one Codex synthesis: N²+N+1 sessions (21 for four
peers), before retries. Native child count and total model calls are unknown in
advance. `run.concurrency` limits top-level subprocesses, not all native children.

- Each initial parent works independently, without other peers' initial reports.
- A critique waits for its author's initial review and the target initial review.
- Every revision waits for all directed critiques, and receives critiques addressed
  to that reviewer.
- Synthesis receives only final peer reviews and pinned source context.
- Critique, revision and synthesis parents can also delegate targeted native checks.
- Children return through native tools. Python does not publish separate child
  report files or independently checkpoint child conversations.
- Missing required delegation produces an INCOMPLETE coverage claim, not a silent
  Python fallback. Delegation summaries and coverage are model claims, not verified
  child telemetry. Requested models are not verified resolved provider models.

## Source map

| Path | Responsibility |
| --- | --- |
| `src/super_review/cli.py` | argparse interface, config selection, executable checks, dry-run and command dispatch |
| `config.py` | Strict TOML validation, defaults and per-role/per-phase inheritance |
| `runner.py` | Persistent top-level dependency graph, report routing, scheduling, retries and protocol version |
| `git.py` | Pinned refs/diff, private Git snapshot, disposable detached worktrees and cleanliness checks |
| `protocol.py` | Run locking, hashes, atomic writes, report metadata and artifact verification |
| `prompts.py` | Common review contract, ten specialties, parent selection policy, phase contracts and shared context |
| `native.py` | Native role definitions, temporary review inputs, collision protection and audit copies |
| `adapters.py` | Harness argv/environment, subprocess lifecycle, bounded output and provider response parsing |
| `skill_install.py` | Shared launcher installation, conflict preflight, backups and legacy installer compatibility |
| `example.toml` | Packaged editable configuration emitted by `init` |
| `skills/super-review/` | Packaged launcher `SKILL.md` and Codex `agents/openai.yaml` metadata |
| `tests/` | unittest suite, fake CLI subprocesses and temporary Git fixtures |
| `docs/` | Design, adapter research, limitations and recorded release verification |

Paths after the first row in the source map are relative to `src/super_review/`
unless explicitly rooted at `tests/` or `docs/`.

Read `README.md` for user behavior, `docs/agent-design.md` and `docs/adapters.md`
for native integration details, and `docs/verification.md` for what was actually
validated. `docs/implementation-plan.md` is historical; it does not override the
current native-agent design. Consult current primary vendor docs before changing
CLI flags or native agent schemas; record consequential compatibility limitations.

## Harness-specific contracts

| Harness key / default executable | Native implementation |
| --- | --- |
| `codex` / `codex` | External role TOMLs registered with `agents.<name>.config_file` and description overrides; `agents.enabled=true`. Parent uses read-only sandbox, never approvals, ephemeral JSON execution, disabled hooks/web. Role TOMLs carry instructions and optional model/effort. Parent sandbox inheritance is essential; role sandbox metadata alone is insufficient. |
| `claude_code` / `claude` | Session-local `--agents` JSON, selected parent `super-review`, named Agent allowlist. Children have Read/Grep/Glob and no Agent tool, with optional model/effort. Plan permissions, strict empty MCP, hooks/slash commands disabled; user auth/settings retained. |
| `cursor` / `agent` (sometimes `cursor-agent`) | Temporary `.cursor/agents/*.md` with `readonly: true`; default Agent mode so delegation is available. Generated `.cursor/cli.json` allows reads and denies writes, shell, MCP and web fetch. No automatic `--trust` or `--force`. Effort uses explicit `effort_models` mappings. |
| `opencode` / `opencode` | Inline primary parent and named subagent JSON definitions; parent task allowlist, children deny further tasks and use read-only permissions. Child variant requires an explicit configured model. Project-config exclusion is requested; global providers/auth/plugins remain trusted. |

Codex/Cursor child instructions prohibit further delegation; do not claim their
role metadata enforces a depth limit. Cursor Ask mode is not the native-parent
profile. OpenCode project-plugin exclusion has a documented upstream limitation;
check the installed release before claiming enforcement. Never weaken permissions
or add bypass flags merely to make a compatibility test pass.

Codex/Claude receive parent prompts on stdin; Cursor/OpenCode read the runtime
prompt file. Every child can read `.super-review-context.md`: pinned commits,
complete diff, requirements and allowed phase evidence, without the parent's task
or delegation instructions. Audit copies and generated definitions are retained in
`logs/<job-id>/<attempt>/`. Reserved input paths are collision-checked; existing
source files, including Cursor's `.cursor/cli.json`, must not be overwritten.

Treat JSON and TOML serialization separately: Codex TOML string values use
`json.dumps(..., ensure_ascii=False)` so non-BMP Unicode does not become illegal
surrogate escapes. Preserve the Unicode prompt/path regression test.

## CLI and configuration

Commands: `init`, `doctor`, `run`, `resume`, `status`, `install-skills`, and the
backward-compatible `install-codex-skill`.

```bash
super-review init
super-review doctor
super-review run --base origin/main --head HEAD --dry-run
super-review run --base origin/main --head HEAD --intent 'What to review'
super-review status /path/to/run-directory
super-review resume /path/to/run-directory
```

Review targets are committed changes only. Base defaults to the merge-base with
head; `--exact-base` selects a direct comparison. No automatic fetch occurs.
`--requirements` reads a UTF-8 file; `--intent` adds optional review guidance.
`--config` selects TOML; otherwise `super-review.toml` is discovered in the invoking
working directory, not automatically under a different `--repo`.

Configuration format version is currently 1. Unknown keys are errors. Settings
inherit harness defaults plus reviewer or phase overrides; synthesis uses Codex
defaults plus `[synthesis]`. Empty native child fields inherit through the harness;
empty parent fields use CLI defaults. Keep `default_config()`, validation,
`example.toml`, documentation and tests consistent when changing settings.

## Launcher skills and installation

`install-skills` defaults to all four harnesses. Codex, Cursor and OpenCode share
one `.agents/skills/super-review` installation. Claude gets identical content in
`.claude/skills/super-review`. Paths are under the user's home, or under
`--project DIRECTORY`. `--harnesses` selects installation targets, not review peers.
Compatible harnesses may discover more than one of these locations.

Invocation: Codex `$super-review`; Claude/Cursor `/super-review`; OpenCode “Use the
super-review skill.” Optional text is forwarded as review guidance. The skill
selects a committed range, invokes the CLI, monitors completion and reads the
combined report. It does not replace the cross-harness handoff schedule.

Keep installed copies identical, protect differing user edits unless `--force` is
explicitly supplied, and keep backups outside discovery roots. Workers receive
`SUPER_REVIEW_WORKER=1`; CLI `run`/`resume` reject recursive wrapper launches. This
must not prevent legitimate native children. The marker is not a security boundary.

Changes to skill resources must remain included by `pyproject.toml` package-data
and `skill_install._contents()`. Codex invocation policy lives in `agents/openai.yaml`;
Claude/Cursor explicit-invocation frontmatter lives in `SKILL.md`. A generic skill
validator may reject vendor extensions; verify them against vendor documentation.

## Persistence and safety invariants

- Pin base/head and save full diff/config/requirements. Do not mix changed inputs
  into an existing run. Default output is `$XDG_CACHE_HOME/super-review/runs` or
  `~/.cache/super-review/runs`.
- Harnesses work in disposable detached worktrees of a private repository copy,
  never the user's source checkout. Disable supervisor Git hooks, remove remotes,
  do not initialize submodules or fetch LFS objects. Changed submodules are rejected.
- Preserve source and runtime-input cleanliness checks, argv arrays without shell
  interpolation, output limits, asynchronous cancellation and process-group cleanup.
- Parse successful terminal provider envelopes, not arbitrary stdout/tool logs.
  Codex must complete its latest turn; Cursor's terminal result may aggregate text.
- Publish metadata-bearing reports atomically; verify hashes and expected identities
  on resume. Preserve exclusive run locking and dependency barriers.
- Resume reruns unfinished parent jobs and their selected children. It does not
  resume individual native children or provider conversations.
- Review protocol is currently 3 (`runner.PROTOCOL_VERSION`). Incompatible prompt,
  adapter or workflow changes require a protocol bump so old/new runs cannot mix.
  Package version, TOML format version and review protocol are separate concepts.
- Product reviewers inspect read-only; they do not execute repository tests/scripts,
  apply fixes, commit or post comments. Maintainers can run the project's tests.
  Read-only harness settings are not an OS isolation guarantee for hostile repos.

## Development and verification

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e . build
python -m unittest discover -s tests -v
python -m build
```

For tests without an editable install: `PYTHONPATH=src:tests python -m unittest
discover -s tests -v` (one shell command). There is no configured linter/type checker.
CI runs unittest, build and version checks on Python 3.11–3.13, Linux and macOS.

Use focused regressions for behavior changes, then the full suite when changing
orchestration, adapters, persistence or packaging. Fixtures exercise real subprocess
and Git boundaries without paid model calls. Never confuse those tests with live
vendor role discovery, authentication or permission enforcement. `doctor` is only
an executable/version check. The 0.5.0 baseline has 55 tests and successful native
tool prompt trials; vendor CLI execution was not available in that environment.
Keep verification claims tied to commands actually run and their scope.

For packaging changes, build both sdist/wheel, install the wheel in a fresh venv,
check `--version`, `init`, a fixture-repository dry run and `install-skills --project`
in a temporary directory. Confirm packaged TOML and skill resources are present.
Do not install into real user skill directories merely to test the installer.

## Publishing changes

1. Inspect status and fetch current `origin/main`; preserve unrelated work and
   integrate concurrent remote changes instead of overwriting them.
2. Make the requested change, update relevant docs/tests and validate proportionately.
3. For a versioned release, keep `pyproject.toml` and
   `src/super_review/__init__.py` versions equal. Documentation-only changes do not
   need a version bump. Update protocol/version compatibility notes when applicable.
4. Commit the intended files and publish through the authorized Git workflow.
   Do not force-push `main`. If using a GitHub API tree/commit/ref workflow, preserve
   paths/modes, use the current remote parent, compare the created tree with the
   local committed tree and update the ref without force.
5. Fetch and verify the published tree matches the reviewed change. Report the
   commit link, verification performed and material untested behavior.

A GitHub main-branch commit makes the change available to Git-URL installations.
Do not invent a release/upload step: no registry credentials or release automation
are configured. Root `AGENTS.md` is included in source distributions via
`MANIFEST.in`; it is maintainer guidance, not an installed runtime skill. Avoid
committing build outputs, virtual environments, credentials, review logs or local
`super-review.toml` files. Follow `.gitignore`.
