# ADR-0003 — The task specification lives on the task branch

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** every MARP repository
- **Refs:** MarineAppliedResearch/MARP#13

## Context

See ADR-0001 for why a GitHub issue is a poor specification. Three problems drove this one
in particular: a commit does not record which version of the spec it implements; CI cannot
assert "no blocking assumption is open" against an issue; and an agent resuming has to
re-read the whole thing rather than a diff.

## Decision

Each task carries `.marp/task.md` on its own branch, with fixed headings so a checker can
parse it, and `.marp/verification.md` alongside it for the G3 test plan. Both die when the
branch merges — a task spec that outlives its task is the stale-assumption problem.

`## Open assumptions` is enforced. `marp spec check` fails while any assumption tagged
`blocking` is unticked, and that check runs as a Claude Code hook, as a pre-commit hook, and
in CI.

The human answers conversationally, in chat or in issue comments, and the agent folds the
answers into the spec. Editing the file directly in the GitHub web editor works and is
supported, but the workflow does not assume it — that was asked and answered on #13.

## Consequences

The specification appears in the pull request, so reviewing the change includes reviewing
what it was meant to do. `git log -p .marp/task.md` shows how the understanding evolved.
The cost is that the spec is invisible until the branch is checked out or opened on GitHub,
which is why the issue remains the human-facing entry point.

