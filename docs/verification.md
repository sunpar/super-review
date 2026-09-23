# Release verification

Version 0.3.0 was reviewed and checked on Linux with Python 3.12 on 2026-09-23.

- 43 automated tests pass, including real CLI fixture subprocesses and temporary
  Git repositories. Four-peer tests cover 12 critiques, incremental scheduling,
  all-critique barriers, final-only synthesis input, concurrency limits, and resume.
- Codex integration tests cover repeat installation, protection and backup of
  customized skills, worker recursion rejection, and literal message forwarding
  through every phase. These tests failed before the implementation was added.
- A fresh agent followed the bundled skill against a fixture-backed repository,
  selected the branch range, passed literal shell-like text safely, completed the
  workflow, and read the combined report. This checks skill usability, not native
  Codex discovery or live provider behavior.
- This audit added regressions for hidden submodule changes, relative harness
  executables, asynchronous checkout responsiveness, checkout cancellation and
  cleanup, cancellation during subprocess creation, and incompatible resume.
  The fixes were verified with failing-then-passing tests.
- Adapter tests check the emitted native agent/tool configurations and canonical
  provider envelopes, including Cursor's aggregate terminal result and an incomplete
  latest Codex turn following an earlier successful turn. They validate adapter
  behavior, not enforcement inside real harness binaries.
- An independent final review found no remaining material Python regression and
  separately exercised cancellation during a real slow Git smudge filter. It found
  an OpenCode project-plugin exclusion regression upstream; the affected-version
  limitation is documented rather than claiming isolation that is not established.
- Wheel and source distributions are built locally. The wheel is installed in a
  fresh virtual environment; CLI entry points, the packaged configuration and the
  bundled Codex skill installer work.
- CI is configured for Python 3.11–3.13 on Linux/macOS. Local verification does not
  establish the result of that remote matrix.

Protocol 2 prevents version 0.1 runs from resuming with different prompt and adapter
policies. Version 0.3 retains compatibility with 0.2 runs. Existing reports are retained; use the original version to finish those
runs or begin a fresh run after upgrading.

Live provider authentication, current model availability, and live model output
quality were not tested: the harness executables are not present in the build
environment. Run a small review after installing and authenticating your harnesses.
Windows users require WSL; native Windows process-group semantics are unsupported.
