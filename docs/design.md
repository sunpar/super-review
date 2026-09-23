# Super Review design

Build an installable Python CLI for an independent, multi-harness code-review panel.
The source conversation specifies Codex, Claude Code, Cursor CLI, and OpenCode;
each enabled harness parent chooses relevant native specialist children with
configurable model and effort, assembles a Markdown review, critiques peers, revises its
own review after all critiques, and lets Codex synthesize the final report.

## Protocol

- Python 3.11+, Git, Linux/macOS/WSL; no runtime Python dependencies.
- One to four review harnesses; Codex is required for final synthesis even when
  it is not a review peer. Ten available native roles by default; parents choose
  which to spawn and explain unused roles.
- A deterministic asyncio supervisor starts fresh CLI subprocesses for every
  top-level review phase. Each parent model chooses, spawns and waits for native
  child agents. Python never creates specialist jobs or child CLI processes.
- A UTC timestamp plus random suffix identifies the entire run. The manifest
  records exact base, merge-base and head SHAs, expanded configuration, expected
  artifact names, artifact hashes, job states, and errors.
- Initial peer parents complete their selected native child work. Directed critiques
  depend on the author's initial review and their target's initial review and
  can overlap other parents still reviewing. Revision waits for ALL directed critiques;
  synthesis waits for ALL finals and receives only final review bodies.
- Publish Markdown with supervisor-owned JSON-compatible YAML front matter via
  atomic rename. Resume verifies hashes and exact expected identities; partial,
  foreign or changed artifacts cannot satisfy dependencies.
- A non-blocking OS file lock prevents two supervisors from running one manifest.
  Timeout, process failure, or cancellation never publishes a successful report.
  Completed parent artifacts survive; resume retries unfinished parent jobs and
  any new native children. Individual child tasks are not separately resumed.

## Git and execution

Review committed changes only. Resolve references once, default to merge-base,
save a complete diff, and copy the Git repository locally without hardlinks or
remotes. Each CLI task runs in a disposable detached worktree of this private
copy. The source checkout is never the CLI working directory. Disable Git hooks
for supervisor operations. Do not initialize submodules or download LFS content.
Document those limitations and reject submodule changes rather than claim coverage.

Use each harness's read-only controls. Never enable permission bypass flags.
Use argument arrays, not shell interpolation. Bound subprocess concurrency,
per-task duration, total duration, and captured output size. Kill POSIX process
groups on timeout/cancellation. Detect tracked or untracked workspace edits.
This is protection against accidental edits, not an OS sandbox for hostile code.

## Configuration and interface

TOML configuration: run limits, enabled harnesses, reviewer selection, common
specialist instructions, per-harness defaults, per-specialty overrides, and
coordinator/critique/revision/synthesis settings. Snapshot prompt overrides and
requirements when creating the run. Model identifiers are user-selected; no
invented universal effort support. Cursor uses an explicit effort-to-model-ID
mapping. Other adapters use documented parent flags and native child settings.

Commands: init, doctor, run (--dry-run), resume, status. Dry-run resolves the
target and produces a plan without starting any model. Output defaults outside
the source repo under the user's cache directory. No automatic PR comments,
fixes, publishing of reviewed code, or post-combine shell hook. The unfinished
sentence in the conversation is not a specified feature.

## Verification

Test configuration errors, adapter commands and real output envelopes, subprocess
timeouts, pinned targets, atomic artifacts, locking, event-driven dependency
ordering, all four harnesses, failure/resume, tamper rejection and fresh-wheel
installation. Fake executables exercise subprocess boundaries without model
credentials. State clearly that live model compatibility requires installed and
authenticated harnesses and is not established by these tests.
