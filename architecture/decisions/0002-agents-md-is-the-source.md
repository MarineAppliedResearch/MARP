# ADR-0002 — AGENTS.md is the tool-neutral source

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** every MARP repository
- **Refs:** MarineAppliedResearch/MARP#13

## Context

Before this, `agents.md` meant three different things in three repositories: generic LLM
behavioural guidance in marp-api, a seven-line pointer in marp-video-player, and a
1,159-line stale API snapshot in marp-inference-worker. `CLAUDE.md` was the real source in
two of them, and `.github/copilot-instructions.md` did not exist anywhere.

MARP uses Claude Code, GitHub Copilot, and ChatGPT through its GitHub connection. Important
engineering knowledge must not live only in a file named after one vendor, and must not be
duplicated three ways where the copies can disagree.

## Decision

`AGENTS.md` in each repository is the single source. `CLAUDE.md` and
`.github/copilot-instructions.md` are pointers to it plus whatever is genuinely specific to
one tool — hooks and permission rules for Claude, path-specific instructions and the
default-branch warning for Copilot.

The top of every `AGENTS.md` carries a shared block, delimited by `marp:shared` markers and
synced from the umbrella's own `AGENTS.md`. `marp harness sync --check` fails on drift and
runs in CI, which is the same trick `marp doctor` already plays on the workspace
`.gitignore`.

Because ChatGPT reaches the code through GitHub rather than a local sandbox, everything an
agent needs must be *visible in the repository*. That is a stronger reason for this than
tool neutrality on its own.

## Consequences

One place to change a platform rule. A component cloned standalone still carries the rules
it needs. The cost is that a drifted copy is now a CI failure rather than a quiet
inconsistency, which is the point.

