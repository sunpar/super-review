# Release verification

Version 0.5.0 was checked on Linux with Python 3.12 on 2026-09-23.

- All 55 automated tests pass. Real fixture subprocesses and temporary Git repositories cover cross-harness barriers, concurrency, report routing, cleanup, cancellation and resume. Four peers now produce 21 top-level jobs and no Python specialist jobs.
- Native definition tests cover Codex TOML registration, Claude named Agent permissions, Cursor role Markdown and read-only project permissions, OpenCode task permissions and model/variant settings, collisions, tampering detection and cleanup. These test emitted configuration, not enforcement inside vendor binaries.
- Independent code review found a Codex JSON-to-TOML Unicode escaping bug. A regression reproduced the failure; the fix preserves non-BMP characters in instructions and role-file paths. The reviewer verified the fix and all seven native-definition tests passed.
- A parent prompt trial on a one-line arithmetic change chose no children, explained each skipped role and reported the concrete defect. This validates the permitted zero-child path without forcing a fixed specialist checklist.
- A second parent trial selected native security and concurrency children for a two-file change, collected both results, verified the authorization and lost-update findings and explained the three unused roles. A session interruption resumed the same children without duplicating them. This validates prompt/tool behavior in this environment, not vendor CLI discovery.
- Existing shared-skill tests cover repeat installation, backups, conflicts, symlink protection, shared destinations, literal optional-message forwarding and recursive wrapper rejection. Earlier fixture-backed skill trials exercised the Codex and Claude-compatible wrapper instructions; they were not tests of native vendor discovery.
- Wheel and source distributions build successfully. The wheel installs into a fresh virtual environment. Its CLI reports 0.5.0; a four-harness dry run exposes 21 jobs, ten native role definitions per parent and a model-selected child count. The installed shared skill copies match across the shared and Claude-compatible destinations.
- CI is configured for Python 3.11–3.13 on Linux/macOS. Local verification does not establish the remote matrix result.

Protocol 3 prevents older fixed-specialist runs from resuming under different orchestration and prompt policies. Finish those runs with their original package version, or start a fresh run after upgrading.

The four vendor harness binaries are not installed in this environment. Live authentication, role discovery, native permission enforcement, provider model availability and review quality have not been verified. Prompt trials use the available native agent tool in this environment; they do not substitute for a small review on each installed vendor harness. OpenCode's documented project-plugin exclusion limitation remains described in the adapter notes. Native Windows process-group semantics are unsupported; use WSL.
