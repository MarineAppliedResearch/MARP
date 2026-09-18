---
task: MarineAppliedResearch/MARP#<n>
repos: [MARP, MARP_API]
status: design
needs: []
---

## Goal

Setting up a workspace — a fresh clone, a second machine, or an agent — gives you a
working MARP with data already in it: the observations, the thumbnails and a login, loaded
from the dump. Tests then run against that database and are free to write to it, because
it is a copy and the dump is the master. Nothing anywhere has to be treated as precious,
and no test can reach a database that is not disposable.

This is the design that was intended when `marp db dump` and `marp db load` were built
(#125) and when the testing database was built (MARP_API#157). Both work. Neither is
called from workspace setup, so every workspace today comes up either empty or pointed at
the one database that holds real work.

## Requirements

- **R1** — `marp setup` on a fresh clone loads the newest dump into the database it just
  built, including the reviewer and administrator logins, so the workspace is usable
  without any further step.
- **R2** — `marp agent start` does the same for an agent's isolated database, with that
  agent's own thumbnail directory (MARP_API#132), so an agent sees the same rows a
  developer does.
- **R3** — A workspace that already has a database keeps it. Setup loads the dump when the
  database is empty and leaves it alone otherwise, so re-running setup is safe.
- **R4** — The Jest suites run against a database that is a copy of the dump. No suite can
  write to a database whose contents are not reproducible from the dump.
- **R5** — `marp db dump` refreshes the master copy from the database in front of you, and
  is the only way a new inference run or a review session becomes part of what other
  workspaces get.
- **R6** — `marp doctor` reports when the database holds work the dump does not, naming
  roughly how much, so unsaved work is visible before something rebuilds the database.
- **R7** — A test run against a non-local database still refuses, as it does today
  (`tests/setup/local-database-guard.js`). Nothing in this task weakens that.
- **R8** — A fresh clone on a machine that has never seen this project can fetch the dump
  with one documented command and nothing copied by hand. **The dump is never committed.**
  It is published as a release asset and cached locally, so no repository grows by the size
  of the test data every time the test data changes.

**Out of scope, deliberately:** CI does not get the dump and does not run the browser
tier. CI stays fast and keeps building an empty database from the baseline and the
migrations; the browser tier runs locally before the pull request. This follows the
existing doctrine that CI runs the fast tiers only and that a green pipeline is not G4.

## Open assumptions

- [x] **A1 · security/permissions · blocking** — answered 2026-09-17: every account in the
  dump is a test account whose password is used nowhere else. The dump may travel and may
  be published. This settles *whether* it can leave the machine; it says nothing about
  *where* it goes, which is A3.

- [x] **A2 · architectural · blocking** — answered 2026-09-17: **one** database per
  workspace. It is loaded from the dump and the tests write to it directly. The accepted
  cost is that running the suite changes the database under an open browser tab.
  `scripts/testing-database.js` provisions a second one today for the browser tier; what
  becomes of it is a question for the plan, not a blocker.

- [x] **A3 · environment · blocking** — answered 2026-09-17: **a GitHub Release asset, and
  never a commit.** The dump is roughly 29 MB and changes whenever the test data changes;
  committing it would add that to permanent history on every refresh and every clone would
  carry it forever. A release asset keeps every repository the size it is now, keeps each
  dump versioned and downloadable, and lets old ones be deleted. `marp setup` fetches the
  newest and caches it under the git-ignored `.marp/local/corpus/`.

  CI is not a consumer: it does not get the dump and does not run the browser tier
  (see *Out of scope*).

- [ ] **A4 · behavioural** — R6's "holds work the dump does not": is comparing row counts
  per table enough to be useful, or do you want it to name what is new (this many
  observations, this many reviews)? Counts are a few lines; naming them is a query per
  table. Not blocking — I will start with counts.

- [ ] **A5 · destructive** — Loading a dump into a database that already holds rows
  replaces them. `marp db load` already refuses this without `-Force`. Setup will load only
  into an empty database (R3) and never pass `-Force` itself. Not blocking unless you
  disagree.

## Decisions

- **2026-09-17** — The dump is a *testing* dump, portable by design. It carries auth
  identities precisely so the same environment comes up on any machine. The guidance in
  `CLAUDE.md` and `AGENTS.md` that it "stays on the machine that made it and is never
  committed" describes it as if it were production credentials, and that framing is what
  has stopped every agent from wiring it into setup. It is wrong for what this file is for
  and gets corrected as part of this task — subject to A1, which is about *where* it may
  live, not *whether* it may travel.

## Plan

1. Correct the dump doctrine in the umbrella's `AGENTS.md` and `CLAUDE.md`. Both
   occurrences are outside the `marp:shared` block, so no component sync and no umbrella
   promotion is needed. Do this first: while it reads *"never committed"* with no
   distinction between publishing a test dump and leaking production credentials, the next
   agent refuses this work for the reason it gives.
2. `marp db publish` — upload the newest local dump as a release asset, and
   `marp db fetch` — download the newest published one into `.marp/local/corpus/` if it is
   not already there (R5, R8).
3. `marp db load` gains a non-interactive path suitable for setup: load into an empty
   database, refuse a non-empty one, no prompt.
4. `marp setup` fetches then loads, after the migrations (R1, R3, R8).
5. `marp agent start` does the same for an agent's database, passing that agent's
   thumbnail directory (R2). `scripts/harness/agent.mjs` documents the opposite today and
   that comment goes with it.
6. `marp doctor` gains the unsaved-work check (R6).
7. **MARP_API:** point the Jest suites at the workspace's dump-loaded database per A2, and
   correct `jest.config.js`, whose header states that tests run against the development
   database as a design choice.
8. **MARP_API:** `tests/thumbnails.test.js` still trips the corpus guard even on a copy,
   because `discardQueue()` deletes every `queued` row and the suite calls it. A copy makes
   that harmless to keep, but the suite still fails, so the guard and that test have to
   agree — scope the delete, restore in `afterAll`, or let the guard treat a reproducible
   database differently. Smallest change wins; decide with the code in front of me.

## Acceptance criteria

- A clone on a second machine reaches a mosaic page with tiles on it using only the
  documented setup command.
- `marp agent start` produces an agent that can run the mosaic browser tier and see rows.
- Running the full Jest suite twice in a row leaves the dump-loaded database able to serve
  the mosaic both times.
- `marp doctor` says something true and specific after a review session that has not been
  dumped.
- CI runs the mosaic browser tier, and it fails when the reviewer is broken.

## Test plan

Filled in at G3.

## Status

- **Gate:** implementing
- **Notes:** Written 2026-09-17 after establishing that `marp agent start` builds an empty
  database by design, that CI runs no browser tests at all, and that
  `tests/thumbnails.test.js` deleted a row from the development database via an unscoped
  `DELETE ... WHERE status = 'queued'` in `discardQueue()`. A1–A3 answered the same day;
  A4 and A5 carry a stated default and are not blocking.

  The umbrella half (plan 1–6) lands here. The `MARP_API` half (plan 7–8) is a second
  branch and a second pull request in that repository, referenced from this task's issue.
