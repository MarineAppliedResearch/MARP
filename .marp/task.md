---
task: MarineAppliedResearch/MARP#132-umbrella
repos: [marp]
status: verifying
needs: []
---

<!--
  The umbrella half of MARP_API#132, authorised after that issue's PR (#160) merged.
  MARP_API now reads THUMBNAIL_STORAGE_DIR; nothing on this side sets it, so the
  commands that move thumbnails can still point the wrong directory at the wrong
  database. That is the whole of this task, plus a question to answer rather than
  build.
-->

## Goal

`marp db load` can no longer replace one database's thumbnails while writing another
database's rows. MARP_API#132 made the thumbnail directory configurable but nothing in
this repository sets it, so a load aimed at a second database with `-DataDirName` still
restores its pictures into whichever directory `MARP_API/.env` happens to name -- which
belongs to the first database. The rows go one place and the JPEGs go another, both
commands report success, and what is left is two databases with broken tiles.

## Requirements

- **R1** -- `marp db dump` and `marp db load` take a thumbnails directory for the database
  they are acting on, and pass it to marp-api as `THUMBNAIL_STORAGE_DIR`, exactly the way
  they already pass `PG_BIN`. `marp.sh`'s spelling matches its existing style.
- **R2** -- Given no such directory, both behave exactly as they do today. An existing
  invocation against the workspace's own database must not change, and must not start
  needing a new flag.
- **R3** -- `load` **refuses** when it is aimed at a second database (`-DataDirName`) and
  no thumbnails directory was named. That is the case that destroys: the directory it
  would replace belongs to a database it is not writing to. The refusal names the flag.
- **R4** -- `dump` **warns** in the same case and continues. It reads rather than
  destroys, so it follows the graduated rule this script already uses for `-Apply` and
  `-Force`: the loud stop is for the destructive half.
- **R5** -- `marp agent start` writes `THUMBNAIL_STORAGE_DIR` into the workspace's `.env`,
  and `marp agent env` prints it. This makes explicit what is currently true only by
  accident, so that anybody -- or any command -- that needs to know where that workspace's
  thumbnails live can read it rather than infer it.
- **R6** -- The value written is **relative**, so a workspace that is moved or copied still
  resolves it. marp-api resolves a relative value against its own repository root.
- **R7** -- `node scripts/harness/check.mjs` is no worse than it was before this branch.

## Open assumptions

- [ ] **A1 · architectural · non-blocking** -- The umbrella names a thumbnails directory
  only when it is *told* one, rather than deriving one. It could compute
  `MARP_API/storage/instances/<name>/observation-thumbnails` and pass it always, which
  would need no new flag — but it would make this repository a second owner of marp-api's
  storage layout, which is the drift `db/corpus.js` avoids by reading `STORAGE_DIR` from
  `config/thumbnails.js` rather than restating the path. The same boundary the header of
  `db.ps1` states twice: this side contributes where PostgreSQL's tools are and which
  database is running, and nothing about marp-api's own files. Recommendation as built.
- [ ] **A2 · destructive · non-blocking** -- `-DataDirName` is the signal for "a database
  other than this checkout's own", not `-Port`. A different port with the same data
  directory is the same cluster reached differently, and somebody whose database is on a
  non-default port because 5432 was taken must not meet a refusal on every load. Two
  clusters need two data directories, so the signal is exact and has no false positives;
  `marp agent start` already passes `--data-dir` for every workspace it makes.
- [ ] **A3 · environment · non-blocking** -- `marp setup`'s `Set-ApiEnvironment` is left
  alone. The main checkout's default is already correct, so writing it would pin a value
  that is better left implicit there, and `setup` rewrites somebody's real configuration
  file. Agent workspaces are different: their `.env` is generated wholesale by this
  repository, so being explicit there costs nothing.
- [ ] **A4 · environment · non-blocking** -- `db up` is not given the variable. It runs
  `init-database.js` and `db:migrate`, neither of which writes an observation thumbnail --
  the one migration that writes files writes species pictures, and the thumbnail migration
  enqueues rows. Adding it there would be a variable set for no reader.

No blocking assumption is open.

## Decisions

- **2026-09-12** -- Agent workspaces do **not** share a thumbnails directory today, and
  this task does not change that. `marp agent start` copies `storage/` into each workspace
  and marp-api's default path is checkout-relative, so each already has its own. Whether
  they *should* share is a real question with a real saving behind it (26 MB each, three
  workspaces), and it is answered in the report as an argument rather than built. See
  *Not covered*.

## Plan

1. `scripts/db.ps1`: a `-ThumbnailDir` parameter; `Invoke-ApiScript` passes it as
   `THUMBNAIL_STORAGE_DIR` when set; `load` refuses and `dump` warns per R3 and R4.
2. `scripts/db.sh`: the same, spelled `--thumbnail-dir`.
3. `scripts/harness/agent.mjs`: write the line into the generated `.env`, and print it in
   `agent env`.
4. Documentation: `db.ps1`'s and `db.sh`'s own headers, and the umbrella's `CLAUDE.md`
   under *Copying the corpus out, and back*. No environment literals.
5. `node scripts/harness/check.mjs`.

## Acceptance criteria

- A load aimed at a second database without a thumbnails directory refuses, names the
  flag, and writes nothing.
- The same load with the flag restores that database's pictures into that database's
  directory and leaves every other directory untouched, verified by file count.
- An ordinary load against the workspace's own database behaves exactly as before.
- A newly generated agent `.env` carries a relative `THUMBNAIL_STORAGE_DIR`.
- The harness check is no worse than at `cc2311e`.

## Test plan

In `.marp/verification.md` at G3. These are shell scripts with no test harness in this
repository, so verification is running them for real — and doing that safely means **dry
runs and refusals only**, never `-Apply`. A refusal stops before anything runs and a dry
run ends before `pg_restore`, so both can be aimed at a real database and prove what they
need to: which directory the report names, and which file count it holds. Nothing is
loaded, and the thumbnail directories are counted before and after.

## Not covered

- **Whether agent workspaces should share one thumbnail store.** Answered as an argument,
  with evidence from the code, and deliberately not built. An overlay scheme is a design
  the human wants to see argued first.
- **`marp setup`** — see A3.
- **The shared `AGENTS.md` block.** Nothing here needs it. Changing it is three steps
  including promoting the umbrella to `master`, and that is not started casually.
- **`marp-api (develop) carries .marp/task.md`**, which the harness already failed on
  before this branch existed. It is the spec from PR #160, unretired. Retiring it means
  committing on another repository's `develop`, which is not this branch's to do.
