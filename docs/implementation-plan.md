# Original implementation plan (historical)

This records the initial fixed-worker implementation. Version 0.5 replaces its
specialist scheduling with [native delegation](native-agent-design.md).

**Goal:** Deliver a public, pipx/uv-installable multi-harness review supervisor.
**Architecture:** Standard-library Python, adapter boundaries, persistent DAG jobs,
isolated Git worktrees and atomic Markdown reports.
**Spec:** [design.md](design.md).

## Global constraints

Python 3.11+, Git, Linux/macOS/WSL. No Python runtime dependencies. Never invoke
shell strings or permission-bypass flags. Codex owns synthesis. Original reviews
are immutable. All model/effort settings are explicit or inherited from the CLI.

## Review focus

Wrong/reused artifact identity; subprocesses surviving cancellation; moving Git
refs; invalid configuration silently ignored; failed harness JSON interpreted as
a successful report. Tests for these belong to the modules below.

## Tasks

1. Configuration and package: write validation/inheritance tests, run them failing,
   implement config.py and pyproject.toml, run tests. Export load_config(path),
   validate_config(dict), settings_for(config,harness,phase,reviewer=None).
2. Harness boundary: tests for argv, stdin, JSON envelopes, explicit model/effort,
   failed results and timeout cleanup; implement adapters.py. Export
   invoke(harness,settings,prompt,cwd,log_dir,timeout,max_output_bytes)->str.
3. Persistent protocol and Git: test locks, atomic writes, SHA pinning and private
   worktrees. Implement protocol.py and git.py; export create_run(...),
   execute_run(path), read_status(path) at the runner interface.
4. Scheduler and prompts: end-to-end tests with real fake subprocesses for four
   peers, incremental critique, global barriers, failure/resume and tampering.
   Implement the DAG and specialist/phase prompts; run the complete suite.
5. CLI/docs/CI: implement init/doctor/run/resume/status, document setup and limits,
   build wheel and sdist, install the wheel in a fresh venv and exercise commands.
6. Fresh independent whole-project review, address material defects, rerun tests,
   commit and publish to a new public repository on the connected GitHub account.

Run tests with `python -m unittest discover -s tests -v`. The empty package first
fails behavioral tests; each task is complete only when its tests and prior tests
pass. Keep implementation and regression tests in the same commit.
