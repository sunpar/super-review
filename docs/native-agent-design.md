# Native review redesign — version 0.5

- Python schedules only top-level peer review, critique, revision and Codex synthesis sessions.
- Each parent receives named native specialist definitions selected from run.reviewers; this is an available catalog, not a mandatory checklist.
- Parent chooses relevant roles, scopes, parallelism and followups; permits no children when justified; reports actual delegation and skipped roles.
- Child model/effort settings continue to inherit harness defaults and per-reviewer overrides. Empty native fields inherit parent settings. Cursor uses existing effort_models map. OpenCode nonempty child effort requires explicit child/default model because variant only applies to configured agent models.
- Native definitions: external Codex role TOMLs registered via CLI overrides, Claude session-local --agents with Agent allowlist, Cursor project agent Markdown plus runtime deny permissions, OpenCode inline subagent definitions with restricted task permissions.
- Separate read-only shared context file gives native children pinned diff, requirements and phase reports without parent delegation instructions.
- Temporary workspace inputs are collision checked, verified after execution and removed; original source is never edited. Runtime definitions are retained in per-attempt logs.
- Peer barrier remains deterministic; native child counts and model calls are unknown before execution. Resume retries a failed parent and its children, not individual children. Protocol bumps to 3.
- Do not claim native runtime/provider compatibility without live binaries. Test emitted schemas, settings propagation, process graph and workspace restoration with fixtures; separately forward-test delegation instructions with actual available child-agent tooling.
