# MARP workspace

This is the workspace root for the MARP ecosystem. Each subdirectory listed below is an independent Git repository. Work here when a change spans more than one component.

`services/repos.yml` is the canonical registry. This file is the operational companion: how to build, run, and test each part, and what currently does not work.

## Getting the workspace

`scripts/marp.ps1 setup` takes a bare clone of this repository to a running
database with a login: clones every component, installs marp-api's
dependencies, writes its `.env`, builds the database, sets the first
administrator's password, and writes the annotation GUI's application token.
Idempotent, so re-running after a failure is the fix.

`scripts/marp.sh` is the POSIX counterpart for everything except `setup`.

`clone` is the default command. Any command takes one repository, by registry
name (`marp-api`) or directory (`MARP_API`).

Four orderings in `setup` are load-bearing, and each was a bug first:

- **npm install before the database.** The database step ends by having
  marp-api load its schema, which needs its dependencies.
- **`.env` before the database.** The bootstrap migration names the first
  administrator from `BOOTSTRAP_ADMIN_NAME` in `.env`. Writing `.env`
  afterwards meant the migration had already defaulted the name.
- **The admin password after the migrations.** The account does not exist
  until they run.
- **The token last.** It needs the permission catalog the migrations seed.

Adding a component means editing `services/repos.yml` and `.gitignore`, not
the scripts. `doctor` fails when those two disagree.

### Which branch gets cloned

`default_branch` in the registry is the branch to **develop on**, not GitHub's
default. They differ: marp-api's GitHub default is `master`, a year and 147
commits behind, with no `routes/` and no `db/baseline/` -- a workspace cloned
from it cannot build its own database, which is exactly what happened.

`develop` for marp-api, marp-inference-worker and video-processing-gui.
marp-video-player and marp-jellyfin have no develop branch and stay on master.

## The database

`marp db up` downloads a self-contained PostgreSQL 18.6 into `.postgres/`,
starts it on 127.0.0.1:5432 and has marp-api load its schema. No installer, no
administrator rights, no VM, no container. `marp db destroy` throws the
database away but keeps the download; `.postgres/` is git-ignored.

Because PostgreSQL lives inside the workspace, the workspace cannot be deleted
while it is running. `marp db down` first.

Two boundaries worth not blurring:

- **The schema belongs to marp-api**, which holds the baseline and the
  migrations. `db up` runs marp-api's own `scripts/init-database.js` and
  `db:migrate` rather than keeping a second copy here, which would drift the
  first time somebody adds a migration.
- **marp-api never learns where its database came from.** It reads five `DB_*`
  variables, as it always has. `db up` is one way to produce a PostgreSQL that
  satisfies them, with no more standing than the VM or a remote server.

On Linux it uses the installed PostgreSQL instead of downloading: the project
publishes no portable Linux build.

### PowerShell traps this script kept falling into

All four cost real time, and all four are silent:

- **`&` on a native command blocks until stdout reaches EOF.** `pg_ctl` exits
  at once but the server it spawns inherits the pipe, so starting the database
  never returned. Started via `Start-Process` now -- and *not* with `-Wait`,
  which waits for the whole process tree including the server.
- **stderr is fatal under `ErrorActionPreference = 'Stop'`.** An `npm notice`
  aborted setup; a `psql` notice killed `db status`. Native calls go through
  `Invoke-Native`, which relaxes the preference and believes the exit code.
- **A function returns everything it emits.** Returning an exit code alongside
  a command's output gives the caller an array, and `-ne 0` filters rather than
  compares -- so a failed step reported success. Exit codes go in
  `$script:LastNativeExit`; output goes to `Out-Host`.
- **Embedded quotes are not escaped for native arguments.**
  `"SequelizeMeta"` reached psql unquoted, was folded to lower case, and
  failed against a healthy database.

## Components

### marp-api — `MARP_API/`

The MARP API and application backend. Also serves the browser applications from `frontend/apps/`. The video player is no longer among them; it moved to its own repository.

- **Runtime:** Node 22.22.1, pinned in `.nvmrc`. Installed via nvm-windows at `C:\nvm4w\nodejs`.
- **Database:** development PostgreSQL runs on the Ubuntu VirtualBox VM `MARP DEV ENVIRONMENT`, reached at `localhost:5433` through a NAT port forward. Database `mare_v1`, role `mare_user`.
- **Config:** `.env` in the repo root, git-ignored. `.env.example` documents every variable.

```bash
cd MARP_API
npm install
npm run dev                      # nodemon, or press F5 in VS Code
npm test                         # 29 suites, 227 tests
npx sequelize-cli db:migrate:status
```

Serves `http://localhost:3000/`, `/api-docs`, `/developer-docs`.

### marp-video-player — `marp-video-player/`

Frame-accurate WebCodecs video player. Extracted from marp-api; the two are
deliberately disconnected, and marp-api does not consume it as a dependency.

- **Runtime:** Node 20+. ESM package (`"type": "module"`), so CommonJS config
  files carry a `.cjs` extension.

```bash
cd marp-video-player
npm install
npm run build        # ESM, IIFE, and minified standalone bundles
npm run serve        # player at http://localhost:8099/app/index.html
npm test             # 140 unit tests, seconds, no dependencies
```

`npm run test:e2e` is a real browser against a real Jellyfin server and takes
minutes. Do not run it for routine feedback; leave it to the person working.

The C# WebView2 host in `VIDEO_PROCESSING_GUI` consumes this player. Its
contract — the `MarpVideoEngine` global, the `postMessage` protocol, and
`app/player.html`'s query parameters — must not change casually. See that
repository's own `CLAUDE.md`.

### marp-video-server — `marp-jellyfin/`

Jellyfin fork, ~93 MB checked out.

**Does not build on this machine yet.** `global.json` pins .NET SDK `9.0.0` with `rollForward: latestMinor`, which stays within major 9. Only SDK 10.0.400 is installed, so `dotnet` refuses to resolve. Installing the .NET 9 SDK is deferred — Jellyfin currently runs on the VM, reached at `localhost:8096`. Revisit when local builds are actually needed.

### marp-inference-worker — `marp-inference-worker/`

Python ML inference service. Requires an NVIDIA GPU to run, not to build.

**The checked-in `.venv` is broken:** it points at `C:\Users\isaac\...\pythoncore-3.11\python.exe`, which does not exist for the current user. Python 3.12.10 is installed at `%LOCALAPPDATA%\Programs\Python\Python312`; the venv needs recreating against it. Deliberately 3.12 rather than the system 3.14, because `torch` and `ultralytics` wheels lag new Python releases.

This directory is owned by Windows user `isaac`, so git needed a `safe.directory` entry. Files are writable.

## Related repositories

### VIDEO_PROCESSING_GUI — `VIDEO_PROCESSING_GUI/`

Legacy Windows desktop annotation client. **Not part of a MARP deployment** — it is here because it consumes the MARP API and must be updated when that API changes.

- **Runtime:** .NET Framework 4.7.2, WPF. Windows-only and permanently so.
- Visual Studio Community 2026 is installed. `msbuild` is not on `PATH`; locate it via `vswhere`.
- Solution: `MAREGUI_PROOFofCONCEPT/MAREGUI_PROOFofCONCEPT.sln`.

## Cross-component work

Every component is its own repository, so a change spanning two of them is two
branches, two pull requests, and two merges. Open a tracking issue in `MARP`
and reference the component issues from it.

The coupling points that matter:

| Between | Contract |
| --- | --- |
| marp-api and VIDEO_PROCESSING_GUI | the HTTP API surface |
| marp-video-player and VIDEO_PROCESSING_GUI | the WebView2 bridge, the `MarpVideoEngine` global, and `player.html`'s query parameters |
| marp-api and marp-video-server | the Jellyfin API |

Nothing detects when a change on one side breaks the other. That gap is known
and untracked.

## How things are wired right now

Facts that are easy to miss and expensive to rediscover.

- **The GUI talks to the development API.** `VIDEO_PROCESSING_GUI/MAREGUI_PROOFofCONCEPT/data/API_IP_ADDRESS.txt` holds `http://localhost:3000`. It is a tracked file, changed to the production address when building for production.
- **Production is a long way behind.** `MARP_API` `master` is over 120 commits behind `develop` and is architecturally older: routes are registered inline in `server.js`, with no `routes/` directory. Rather than backporting into that older shape, the plan is to promote `develop` wholesale -- so `MARP_API#49`, which tracked a narrow keyframe hotfix, was closed in favour of one release. Ten auth/permissions migrations have never run on production and will apply during it.
- **Node needs to be on PATH explicitly** in a shell that was started before nvm-windows was installed. The nvm symlink is at `C:/nvm4w/nodejs`; prepend it. In VS Code, fully quitting and reopening fixes it.
- **Building the GUI from a terminal** needs `msbuild` located through `vswhere`, and output redirected away from the repository. See that repository's own `CLAUDE.md`.
- **Playwright's browser is installed** on this machine already; a new machine needs `npx playwright install chromium` once.

## Known gaps

- `marp-jellyfin` cannot be built locally (needs .NET 9 SDK). Deferred deliberately; it runs on the VM.
- `MARP_API` has 4 moderate dependency advisories left on `develop`, all in the
  sequelize chain, where npm's suggested fix is a downgrade to sequelize 3. Left
  deliberately; see `MARP_API#58`.
- `marp-inference-worker` virtualenv needs recreating against Python 3.12.
- No cross-component build or test command exists; each component is built on its own.
- Nothing verifies the GUI still works against a changed API or a changed player.
- The API repository was renamed `MARE_API` -> `MARP_API`. GitHub redirects the
  old name, so a stale reference works until somebody creates a new repository
  called `MARE_API`. Always write `MARP_API`.
