# MARP workspace

This is the workspace root for the MARP ecosystem. Each subdirectory listed below is an independent Git repository. Work here when a change spans more than one component.

`services/repos.yml` is the canonical registry. This file is the operational companion: how to build, run, and test each part, and what currently does not work.

## Getting the workspace

`scripts/marp.ps1` (Windows) and `scripts/marp.sh` (POSIX) read the registry and
manage every component repository. `clone` is the default, `status` and `pull`
work across all of them, and `doctor` checks the workspace is sound --
including that every component directory is ignored here, so a commit in the
umbrella can never absorb one. `doctor` exits non-zero on failure.

Any command takes one repository, by registry name (`marp-api`) or by directory
(`MARP_API`).

Adding a component means editing `services/repos.yml` and `.gitignore`, not
editing the scripts. `doctor` fails when those two disagree.

## The database

`marp db up` (scripts/db.ps1, scripts/db.sh) downloads a self-contained
PostgreSQL 18.6 into `.postgres/`, starts it on 127.0.0.1:5432 and has marp-api
load its schema. No installer, no administrator rights, no VM, no container.
`marp db destroy` throws the database away; `.postgres/` is git-ignored.

Two boundaries worth not blurring:

- **The schema belongs to marp-api**, which holds the baseline and the
  migrations. `db up` runs marp-api's own `scripts/init-database.js` and
  `db:migrate` rather than keeping a second copy of the schema here, which
  would drift the first time somebody adds a migration.
- **marp-api never learns where its database came from.** It reads five `DB_*`
  variables, as it always has. `db up` is one way to produce a PostgreSQL that
  satisfies them, with no more standing than the VM or a remote server, and it
  need never be run.

On Linux it uses the installed PostgreSQL instead of downloading: the project
publishes no portable Linux build. `.env` is printed, never written -- that
file also holds Jellyfin credentials and a session secret.

Node not being on `PATH` is a routine state here, not a broken machine, so the
script names it rather than blaming the migration script for it.

## Conventions

These apply to every repository in this workspace.

- **Commit authorship is the human developer only.** Never add Claude as author or co-author, and never add a `Co-Authored-By` trailer. This applies to merge and squash commits too.
- **Keep commit messages short.** A subject line under ~72 characters plus a few one-line bullets. Reference the issue with `Refs #NN`.
- **Issues live where the code changes.** Cross-repo work gets a tracking issue in the `MARP` repo, referencing component issues as `MarineAppliedResearch/<repo>#<n>`.
- **Never commit `.env` files or credentials.** Each component has a `.env.example` where applicable.
- Component repositories keep their own `agents.md` / `CLAUDE.md` for specifics. This file holds only what is shared.

### The production database is a scientific record

`mare_v1` in production holds years of annotation that is queried directly and
reported on, by people and by tools outside this workspace. Treat it as a
scientific record, not as application storage.

Any transformation of existing data must either **preserve everything currently
possible**, or transform it so that **nothing is lost** -- a column that stops
being populated, a value that becomes ambiguous, or a format that an existing
query no longer parses all count as loss, even when the application still works.

Derived columns are part of the contract. Something outside the application very
likely reads them.

**Ask about assumptions rather than inferring them from the data.** How a field is
meant to work, what a value means when it is empty, whether two rows that look
like duplicates are one thing or two -- these are answerable by the person who
recorded them and not reliably by inspection. A migration built on a guess about
meaning is the expensive kind of wrong.

Every data migration carries a before/after integrity check (`db/data-integrity.js`
in `MARP_API`) and a `down` that restores what it changed.

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
