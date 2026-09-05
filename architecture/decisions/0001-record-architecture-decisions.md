# ADR-0001 — Record architecture decisions

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** every MARP repository
- **Refs:** MarineAppliedResearch/MARP#13

## Context

Design decisions have been living in GitHub issues. `MARP_API#68` is the clearest example
and it worked: one place, always current, both parties could read it, and it had a stable
address. At 100 KB it also shows the limits — an agent resuming cannot see what changed, and
settled decisions, open questions and implementation status are interleaved with nothing
marking which is which. `MARP_API/CLAUDE.md` had to carry the sentence *"the schema
decisions are settled — see #68, answered 2026-09-05"* precisely because the issue could
not say that about itself.

## Decision

Durable decisions are recorded as short, dated, numbered files in the repository:

- `docs/decisions/` for a decision inside one repository;
- `architecture/decisions/` in the umbrella for a decision about how two or more
  repositories interact.

A decision record is immutable once accepted. Changing your mind means a new record that
supersedes it, not an edit — the reasoning that was current at the time is the thing worth
keeping.

The issue keeps the conversation and the goal. The task specification
(`.marp/task.md`, ADR-0003) keeps the work in flight. Neither replaces this.

## Consequences

Someone reading the code can find out why it is shaped that way without reading a year of
issue comments. The cost is a small file per decision and the discipline of writing it at
the moment the decision is made, which is the only moment the reasoning is still to hand.

