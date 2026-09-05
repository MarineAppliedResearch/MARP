# ADR-0004 — Gitflow, and master means production

- **Status:** accepted
- **Date:** 2026-09-05
- **Scope:** every MARP repository
- **Refs:** MarineAppliedResearch/MARP#13

## Context

`MARP_API`'s GitHub default branch is `master`, which is roughly 147 commits and a year
behind `develop`, has no `routes/` directory, and cannot build its own database. This looks
like decay and is not: `master` is what is in production, production is promoted by hand,
and it has not been promoted in a while.

The distinction matters because an agent that starts from GitHub's default branch starts on
year-old production code, and both the Copilot coding agent and ChatGPT's GitHub connection
do exactly that unless told otherwise. During this investigation the discrepancy was
misread as staleness to be cleaned up, and a rollout plan was built on that error.

## Decision

The branch model is Gitflow. `master` is production and is promoted deliberately by a human.
`develop` is integration. Every task branches from `develop` and is named for its issue.

`services/repos.yml`'s `default_branch` field is authoritative for which branch to work on,
and it is not always GitHub's default. Every agent instruction file says so, and the harness
tooling reads the registry rather than asking GitHub.

No branch promotion is a prerequisite for anything in the harness.

## Consequences

`MARP_API`'s `master` being far behind stops being a defect to fix and becomes a fact to
respect. Tools that cannot be told which branch to start from are a known hazard rather
than a surprise.

