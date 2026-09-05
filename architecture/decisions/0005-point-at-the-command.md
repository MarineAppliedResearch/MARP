# ADR-0005 — Instruction files point at commands, not values

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** every MARP repository
- **Refs:** MarineAppliedResearch/MARP#13

## Context

The umbrella's `CLAUDE.md` described the development database in two contradictory ways
sixty lines apart: one section documented `marp db up`, and the component section sixty
lines later named a VirtualBox VM and a port forward. Four of the five places an agent
would look said VM; only one said `db up`. An agent read the contradiction, resolved it
toward the stale half because three sources corroborated it, and built a plan on the
conclusion that parallel development was blocked. It was not.

`scripts/marp.ps1` already contained a comment acknowledging that `DB_PORT=5433` in
`.env.example` was documentation about a VM port forward rather than a setting. The tooling
was working around the stale documentation instead of the documentation being fixed.

## Decision

Instruction files do not restate environment facts. A host, a port, a path or a version
written into prose goes stale silently and no reader can tell. Write the command that
prints the current value: *"run `marp db status`"*, not *"it listens on 5432"*.

The same rule retires any document that promises to stay in sync with code it cannot
observe — hand-written `## Current API` sections, and change logs of an agent's own
sessions. Point at the generated contract instead.

`scripts/harness/doc-check.mjs` enforces it: it fails on database literals, on the retired
VM markers outside a section flagged `<!-- harness:history -->`, and on credentials.

## Consequences

Documentation says less and stays true longer. A section that genuinely describes a retired
setup is marked as history rather than deleted, so the knowledge survives without reading
as instructions. The check is deliberately narrow — a check with false positives teaches
everyone to ignore it.

