---
name: super-review
description: Use when the user explicitly invokes super-review or requests the installed Super Review swarm, optionally with a review-focus message. Not for ordinary individual review tasks or use inside a swarm worker.
disable-model-invocation: true
---

# Super Review

Launch the installed `super-review` CLI from the user's controlling harness session.
Python manages the reviewers, critiques, revision barrier, and final synthesis.
The launching harness does not select review peers; Codex still performs synthesis.

## Invocation

- Codex: `$super-review [optional review guidance]`.
- Claude Code and Cursor CLI: `/super-review [optional review guidance]`.
- OpenCode: ask `Use the super-review skill` and optionally add review guidance.

Without guidance, review the current branch with the existing configuration.
Text such as `Focus on SQL joins and race conditions` is guidance, not a change to
enabled harnesses or a path filter. Use only the user's actual invocation text,
not the examples here. Claude Code appends supplied arguments as `ARGUMENTS:`;
treat that appended value as the optional message, excluding the label itself.
OpenCode may load this skill automatically; execute only if the user explicitly
requested this swarm. Loading a skill alone is not authorization to run it.

## Execute

1. Check `SUPER_REVIEW_WORKER`. If it is `1`, return to the assigned review;
   do not start another swarm or clear the marker. Check that `super-review` is
   on PATH. If missing, explain the installation requirement instead of simulating
   a swarm: `pipx install git+https://github.com/sunpar/super-review.git`.
2. Work from the target Git repository root. Read its `super-review.toml` if present;
   preserve its harness/model settings. Without one, the CLI uses Codex and all ten
   specialists. Honor an explicitly supplied config or harness selection.
3. Establish the committed range. Use the user's explicit base/head or a base
   already established in the conversation. Otherwise inspect the local default
   branch (`origin/HEAD`, then available `origin/main`, `origin/master`, `main`,
   `master`) and use a base with changes through HEAD. If none has branch changes,
   review the last commit with `--base HEAD~1` when it exists. Announce the selected
   range before execution. Never fetch, commit, stash, or alter files to create it.
   If the user requests uncommitted changes, a whole-repository audit, or an
   unavailable/ambiguous range, explain the committed-diff limit and ask for a
   supported range. Do not silently substitute a different scope. Mention excluded
   dirty/untracked changes; a focus message is guidance within the diff.
4. Pass the optional message verbatim using one `--intent=<message>` argument
   (the equals form also handles messages starting with a hyphen). Without a message,
   omit that argument. Use an argument-array subprocess call with no shell, or
   correctly shell-quote every argument. Never interpolate prose into shell code.
   For a long message, write it with a file-writing tool to a temporary UTF-8 file
   and pass `--requirements` instead. Remove only that temporary file afterward.
5. Run `super-review run --base <base> --head <head>` with the selected arguments.
   Use `--exact-base` for an explicitly requested two-commit comparison. A
   `--dry-run` can preview the target and job count without model calls; it does not
   execute the review. Respect the host's execution/network/approval requirements;
   do not bypass them. This launches provider calls using installed harness logins.
6. Keep the process alive and monitor it using the host's process/session tools.
   Continue waiting when a tool yields a session ID; do not relaunch the swarm.
   On interruption, show the recorded run directory and use `super-review resume`
   only for that run. On failure, report the error and retained logs, not a review.
7. After successful exit, read the emitted combined-review Markdown path. Return a
   concise findings summary and the report path/link. Distinguish COMPLETE from
   INCOMPLETE coverage using the report's own claims; job completion alone does not
   establish coverage. If the report omits a coverage status, say it is unspecified.
   Do not automatically apply fixes or post findings externally.
