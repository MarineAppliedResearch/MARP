# ADR-0006 — marp-jellyfin stays outside the harness

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** marp-jellyfin
- **Refs:** MarineAppliedResearch/MARP#13

## Context

`marp-jellyfin` is a 93 MB fork of upstream Jellyfin. It inherits upstream's own `.github/`
— issue templates, CODEOWNERS, renovate configuration and workflows — and it does not build
on the current development machine, which has .NET SDK 10 where `global.json` pins 9. The
MARP-specific surface is a small number of patches, applied on one remote machine.

## Decision

The harness is not installed there. No `AGENTS.md`, no hooks, no workflows. `marp harness
check` and `sync` skip it explicitly.

What we want instead is documentation, in the umbrella, of the fact that MARP runs a
Jellyfin fork and what has been changed in it.

## Consequences

Nothing fights upstream's repository conventions. If local Jellyfin development becomes
routine, this decision gets superseded rather than quietly eroded.

