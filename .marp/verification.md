# Verification — MARP#132-umbrella

Run 2026-09-12 in the umbrella checkout, on branch `132-thumbnail-dir-umbrella`.

**Nothing in this verification wrote to any database or moved any file.** Every load was
either refused before it ran or a dry run, which `scripts/load-corpus.js` ends with
`Dry run -- nothing written` before it reaches `pg_restore`. The four thumbnail
directories on this machine were counted before and after every run below and are
unchanged at 2,079 files each.

## What each test proves

| Requirement | Test | Tier | Proves |
| --- | --- | --- | --- |
| R1 | `db load … -Port -DataDirName -ThumbnailDir`, dry run | real invocation | the variable reaches marp-api: the report counts the *named* directory, not the default |
| R1 | `marp.sh db load … --thumbnail-dir`, dry run | real invocation | the POSIX side does the same |
| R2 | `db load <dump> <thumbs>` with no new flags, dry run | real invocation | the ordinary invocation is unchanged and meets marp-api's own refusal as before |
| R2 | `marp.sh db load <dump> <thumbs>`, dry run | real invocation | same on the POSIX side |
| R3 | `db load … -DataDirName` with no `-ThumbnailDir` | real invocation | refused, names the flag, nothing run |
| R3 | `marp.sh db load … --data-dir` with no `--thumbnail-dir` | real invocation | same |
| R4 | code + the `second_database` predicate | reading | `dump` warns and continues — **not run against a second database, see below** |
| R5, R6 | `node --check`, `agent list`, `agent env` | parse + run | the module still loads and runs; the generated content is **not** proven — see *Requirements with no test* |
| R7 | `node scripts/harness/check.mjs` | harness | exit 0 |

Both scripts were parse-checked before anything was run: `bash -n scripts/db.sh`, and
`[Parser]::ParseFile` for `scripts/db.ps1`.

## Real results, verbatim

### R3 — the refusal, which is the whole point

```
> powershell -File scripts/db.ps1 load <dump> <thumbs> -Port 5451 -DataDirName MARP_API--157-retire-fixture

==> Loading a corpus dump
    Refused: this is the 'MARP_API--157-retire-fixture' database and no -ThumbnailDir was given.

    Nothing has been changed. A load replaces the whole thumbnails directory,
    and without this it would replace the one MARP_API\.env names -- which
    belongs to a different database. Say where this one keeps its pictures:
        marp db load <dump> <thumbnails-dir> -Apply -ThumbnailDir <path>
    A relative path resolves against the MARP_API repository root.
```

**That exact invocation is the one that used to destroy the development corpus's
pictures** while writing an agent database's rows.

The POSIX side, same invocation shape:

```
==> Loading a corpus dump
    Refused: this is the 'MARP_API--157-retire-fixture' database and no --thumbnail-dir was given.
```

### R1 — the variable actually arrives

A probe directory holding **3** files, against a default holding 2,079, so the two cannot
be confused:

```
> ... -DataDirName MARP_API--157-retire-fixture -ThumbnailDir <probe>

         3  thumbnail files

Note: no rows here, but 3 thumbnail files are on disk.
They are orphans -- nothing in mare_v1 names them -- and a load
replaces them. Their directory is C:\...\scratchpad\thumbs-probe
(THUMBNAIL_STORAGE_DIR, or its default). If that is not the directory you
meant, stop now: the rows that name these files are in another database.

Dry run -- nothing written.
```

marp-api names the probe directory and counts its three files. Without the flag it reports
2,079 and names the default. The POSIX side prints the same three lines.

### R2 — the ordinary invocation is untouched

```
> powershell -File scripts/db.ps1 load <dump> <thumbs>          # no new flags

      2079  thumbnail files

Refused: this database already holds a corpus, and a load replaces it.
...
If you really do mean to replace what is in there, say so: -Force
```

No new refusal fires; it reaches marp-api's own guard exactly as before, reading the
default directory. The POSIX run produced the same, ending `--force`.

### The POSIX side failed first, and the failure is worth keeping

```
/c/.../scripts/db.sh: line 462: THUMBNAIL_STORAGE_DIR=/c/.../thumbs-probe: No such file or directory
```

Written as `${THUMBNAIL_DIR:+THUMBNAIL_STORAGE_DIR="$THUMBNAIL_DIR"}` in the command
prefix. **A command-prefix assignment has to be literal**: that expansion does not
conditionally set a variable, it produces a word the shell then runs as the command. It is
now an `export` inside a subshell — `if` rather than `&&`, because `set -eu` is on and a
false `&&` chain would end the subshell. The reason is written into the code.

The PowerShell side never had this: it builds a hashtable and adds a key.

### R7 — the harness

```
> node scripts/harness/check.mjs
...
==> Harness check
harness check exit: 0
```

### Nothing moved

```
MARP_API: 2079
MARP_API--151-phone-top-chrome: 2079
MARP_API--157-retire-fixture: 2079
MARP_API--137-commit-marked-pager: 2079
```

Counted after every run above.

## Requirements with no test

- **R4, the `dump` warning.** The predicate and the message are shared with the `load`
  refusal, which is exercised on both platforms, but the warning itself was not triggered
  against a second database. Doing it means running a real `dump` of an agent's database,
  which writes a dump directory and reads 26 MB — harmless but not nothing, and one of
  those agents is being worked in.
- **R5 and R6, the generated `.env`.** The two lines added to `agent.mjs` are proven to
  parse and the module still runs (`agent list`, `agent env`), but **no `.env` was
  generated by a real `marp agent start`**, because that creates a fourth PostgreSQL
  cluster, a new branch in marp-api, an 82 MB `storage/` copy and a full `npm ci` — with
  an agent actively working in one of the existing workspaces. The next real
  `marp agent start` proves it for free; what to look for is a
  `THUMBNAIL_STORAGE_DIR=storage/observation-thumbnails` line under the `DB_*` block.
  The three existing workspaces predate the change and correctly do not have it: their
  `.env` is silent and marp-api's default is that same value.

## Edge cases

- **`-Port` alone is not a second database.** A different port with the same data
  directory is the same cluster reached differently, so the refusal keys on
  `-DataDirName`. Somebody whose database sits on a non-default port because 5432 was
  taken meets no refusal — verified by the R2 run, which used neither flag.
- **A relative `-ThumbnailDir`** resolves against the MARP_API repository root, not the
  working directory, because that is what marp-api does with the variable. The messages
  say so.
- **An absolute `-ThumbnailDir`** is used as given — the R1 run used one.
- **`db up` is not given the variable**, deliberately: it runs `init-database.js` and
  `db:migrate`, neither of which writes an observation thumbnail.

## Regression coverage

The failure this branch exists to prevent has no automated test anywhere — these are shell
scripts and this repository has no test harness for them. The R3 runs above are the
evidence, and they are the exact invocation that previously did the damage. If that ever
needs to be a real test, the cheap version is a dry run asserting which directory the
report names.

## Known gaps

- **`marp setup`'s `Set-ApiEnvironment` is unchanged** (A3). The main checkout's default is
  already correct and `setup` rewrites somebody's real configuration file.
- **The sweep for other `DB_*` handoffs found four sites and no others**: `db.ps1`'s
  `Invoke-LoadSchema` and `Invoke-ApiScript`, and `db.sh`'s `load_schema` and `api_script`.
  `marp.ps1` touches `DB_*` only in `Set-ApiEnvironment`; `marp.sh` has no `setup` and no
  equivalent. `agent.mjs` writes the `.env`. Nothing else runs a marp-api script with a
  database in its environment.
- **`marp-api (develop) carries .marp/task.md` is still true**, and the harness is green
  only because that checkout is currently on another branch — `spec-placement.mjs:46`
  skips a repository whose checked-out branch is not an integration branch. The file is
  still tracked on `develop` (`git ls-tree develop -- .marp/task.md`), so the failure
  returns the moment somebody checks that repository back onto develop. Retiring it means
  committing on another repository's `develop`, which is not this branch's to do.
