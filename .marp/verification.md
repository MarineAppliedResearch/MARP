---
task: MarineAppliedResearch/MARP#<n>
repos: [MARP, MARP_API]
ran: 2026-09-17
---

## What this covers

Every requirement in `.marp/task.md` except where noted. These are workspace commands
rather than a test suite, so the evidence is a real run against a real database in each
case — a scratch one where the run is destructive, this machine's own where it is not.

**Not covered, and deliberately:** CI. The dump does not reach it and the browser tier
does not run there; see *Out of scope* in the task. Nothing here asserts anything about
a GitHub runner.

## R1 — setup loads the dump

Setup itself was not run end to end, because it clones five repositories over a
connection and rebuilds a workspace that is already here. The three steps it performs
were run individually against a scratch database instead, which is the same sequence with
the clone and the `npm install` removed.

```
marp db up      -Port 5481 -DataDirName setup-verify
marp db load    <dump> <tiles> -Apply -Port 5481 -DataDirName setup-verify -ThumbnailDir <scratch>
marp db up      -Port 5481 -DataDirName setup-verify        # migrate forward
```

Built empty, then:

```
In it now:            0 observations   0 keyframes   0 thumbnails
In the dump:       2091 observations  29663 keyframes  2090 thumbnails  873 reviews
Loaded:            2091 observations  29663 keyframes  2090 thumbnails  873 reviews
Round trip verified: every count matches the manifest.
```

Then `No migrations were executed, database schema was already up to date.` — the dump is
current, so the third step is the no-op it should be. Queried afterwards:

```
2091 observations | 873 reviews | 2090 thumbnails | 35 users | 2 auth_identities | 854 species
```

2,079 thumbnail files landed in the scratch directory. The main workspace's directory was
unchanged at 2,079 — which is the `-ThumbnailDir` isolation working, and the reason the
scratch run proves anything.

Scratch database destroyed afterwards.

**Gap, stated rather than hidden:** the migrate-forward step was exercised only in its
no-op form, because no migration has landed since the dump was taken. The branch that
actually applies migrations after a load has not been run.

## R2 — agent start loads the dump

`marp agent start marp-api corpus-load-trial` — **result pending at the time of writing.**
This is the one requirement whose verification had not finished. It must not be marked
done from the fact that the code resembles R1's.

## R3 — an existing database is kept

`marp db up` against a database that already exists:

```
database mare_v1 already exists
schema already present, so the baseline was not reapplied
```

`marp db fetch` run twice:

```
20260917-171643 fetched
20260917-171643 is already here
```

## R4 — the suites run against a copy

Satisfied structurally rather than by a new mechanism: R1 and R2 make every workspace
database a load of the published dump, and the suites read `DB_*` as they always have.
A2 settled that there is one database per workspace and the tests write to it.

The half that needed work is the suite that wrote to rows it did not own — see R4b.

**Not verified:** that a workspace built only by `marp setup` runs the suite green. That
needs a from-scratch setup, which is the same run R1's gap describes.

## R4b — a suite may not take a queued row it did not create

The defect that started this: `npm run test:mosaic` failed with

```
observation_thumbnails: 1 row(s) deleted that the suite did not create (2091 -> 2090)
```

Observation 920 — a real row, written 2026-09-10 — lost its thumbnail record. Cause:
`stop` is `discardQueue()`, one unscoped `DELETE FROM observation_thumbnails WHERE
status = 'queued'`, and `tests/thumbnails.test.js` calls it twice.

Reproduced deliberately before the fix by re-enqueuing 920, then:

| run | result |
|---|---|
| before the fix | `1 row(s) deleted that the suite did not create` |
| first attempt (columns) | `row(s) modified, count unchanged at 2091` — timestamptz lost its microseconds through a JS Date |
| after the jsonb round trip | `81 passed, 0 failed` |

Observation 920 afterwards, with its original `requested_at` intact:

```
920 | queued | 2026-09-18T00:38:40.906Z | candidate_index 0 | request_priority 0
total thumbnail rows: 2091
```

Then the whole group: `npm run test:mosaic` → **7 suites passed, 274 tests passed**.

The middle row of that table is the point. The first fix restored the row and still
failed, and only the guard caught the difference — a restore that looks right and is
wrong by a fraction of a millisecond is exactly what this guard exists for.

## R5 — dump refreshes the master copy

`marp db dump` against this machine's database:

```
2091 observations | 29663 keyframes | 2090 thumbnails | 873 reviews | 61 gpu_jobs
2079 thumbnail files
-> .marp/local/corpus/20260917-171643
```

873 reviews against the previous dump's 555, so it picked up work done since.

## R6 — doctor reports what the dump lacks

Both branches were run, because a warning nobody has watched fire is not a warning.

Against the current dump:

```
Work the dump does not have
  ok    nothing here that 20260917-171643 does not have
```

Against the older 2026-09-12 dump, reached by moving the newest aside:

```
Work the dump does not have
  note  this database is ahead of 20260912-165442: observation_reviews +318
         Keep it with:  marp db dump   then   marp db publish
```

873 − 555 = 318. A note, not a failure — `doctor`'s exit code was unchanged by it.

## R7 — a non-local database is still refused

Untouched by this work. `tests/setup/local-database-guard.js` has its own test and
neither was modified; `git diff` over this branch shows no change to either file.

## R8 — a fresh clone can fetch the dump

Published, then the local copies were moved aside so `fetch` had to go and get it:

```
marp db publish   ->  corpus-20260917-171643
                      https://github.com/MarineAppliedResearch/MARP_API/releases/tag/corpus-20260917-171643
(local corpus/ moved away)
marp db fetch     ->  Downloading corpus-20260917-171643
                      20260917-171643 fetched
```

What came down: `corpus.dump`, `manifest.json`, and 2,079 thumbnail files — 29 MB,
complete. The older local dumps were put back afterwards and all four are on disk.

## Defects found and fixed while verifying

- **`marp db load` could not reach a second database at all.** `-ThumbnailDir` existed on
  `db.ps1` and was never declared on the `marp` wrapper, so the flag was dropped and every
  load into a `-DataDirName` database refused — while `MARP_API/AGENTS.md` said to run
  exactly that command. Found by R1's scratch run failing. Fixed in both scripts and the
  paragraph corrected.
- **`Invoke-Counts` returned an array.** `Write-Output` followed by `return $true` makes a
  PowerShell function return both — the trap `CLAUDE.md` documents, walked into anyway.
  Caught by reading, before it shipped.
- **An array passed positionally does not spread into `ValueFromRemainingArguments`.** The
  table names arrived as one item, the identifier filter dropped them, and `doctor`
  reported "the database is not running" against a running database. Splatted now.

## Left alone, and why

- 16 stopped agent data directories, roughly 1.4 GB. `marp agent remove` clears them but
  throws away working copies, which is a person's decision.
- `marp-inference-worker-0.1.0-windows-x64-setup.exe`, 69 MB, untracked in the workspace
  root. `marp doctor` is red for it. It is a build artifact, not this task's.
- `marp harness check` is red: the shared block in `MARP/AGENTS.md` changed, so all four
  components report drift until the umbrella reaches `master` and `marp harness sync` runs.
  That is the documented three-step, not a break.
