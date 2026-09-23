# Release verification

Version 0.1.0 was developed and checked on Linux with Python 3.12.

- 28 automated tests pass, including real CLI fixture subprocesses and temporary
  Git repositories. Four-peer tests cover 12 critiques, incremental scheduling,
  all-critique barriers, final-only synthesis input, concurrency limits, and resume.
- A fresh reviewer inspected the whole implementation and reproduced two Git
  defects: borrowed object storage in snapshots and missed submodule deletions.
  Both were fixed with failing-then-passing regression tests.
- Adapter regressions exclude intermediate Cursor/OpenCode progress text from
  reports and reject explicit error/incomplete provider envelopes.
- Wheel and source distributions are built locally. The wheel is installed in a
  fresh virtual environment; CLI entry points and the packaged configuration work.
- CI is configured for Python 3.11–3.13 on Linux/macOS. This is a configured matrix,
  not a claim that those remote jobs ran before the repository was published.

Live provider authentication, current model availability, and live model output
quality were not tested: the harness executables are not present in the build
environment. Run a small review after installing and authenticating your harnesses.
Windows users require WSL; native Windows process-group semantics are unsupported.
