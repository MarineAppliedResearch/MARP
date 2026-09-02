# MARP Platform

MARP (Marine Analysis and Reporting Platform) is composed of multiple independently maintained applications and services. This repository is the umbrella repository for the MARP ecosystem: it is the workspace root, and it holds architecture, deployment, development setup, compatibility information, and system-level documentation.

The goal is a single system that builds easily and can be worked on as a whole, rather than a set of repositories that each have to be discovered and configured by hand.

## Getting the whole workspace

Clone this repository and run one command. It clones every component, installs what the API needs, builds a database with the MARP schema in it, creates a login, and hands the annotation GUI an application token.

```powershell
git clone https://github.com/MarineAppliedResearch/MARP.git
cd MARP
.\scripts\marp.ps1 setup
```

```bash
git clone https://github.com/MarineAppliedResearch/MARP.git
cd MARP
sh scripts/marp.sh clone      # setup is Windows-only for now; see below
```

`setup` prompts for a password for the first administrator. To run it unattended:

```powershell
.\scripts\marp.ps1 setup -AdminName "Your Name" -AdminUsername you -AdminPassword secret
```

Then start the API:

```powershell
cd MARP_API
npm run dev                   # http://localhost:3000
```

Log in with the username you gave. `/api-docs` and `/developer-docs` are served from the same place.

Expect around 640 MB of repositories plus a 330 MB PostgreSQL download the first time. Every slow step reports progress, so a quiet minute means something is wrong rather than working.

`setup` is idempotent: it skips whatever is already done, so it is safe to re-run after fixing whatever stopped it.

### What setup actually does

1. Clones every repository in `services/repos.yml`, at the branch the registry names.
2. Installs `marp-api`'s dependencies — **before** the database, because the database step finishes by having `marp-api` load its schema.
3. Writes `MARP_API/.env`: the database settings, a generated `AUTH_SESSION_SECRET`, and `BOOTSTRAP_ADMIN_NAME`. This happens before the database is built, because the bootstrap migration reads that name when it creates the first administrator.
4. Downloads and starts PostgreSQL, then has `marp-api` restore its baseline schema and run its migrations.
5. Gives the first administrator a password. The bootstrap migration deliberately sets none — a password hash in a committed migration would be a credential in source control — so without this step the only administrator holds every permission and cannot log in.
6. Mints the `annotation-gui` application token and writes it to `VIDEO_PROCESSING_GUI/MAREGUI_PROOFofCONCEPT/data/MARP_API_TOKEN.txt`, which is git-ignored there. Every route requires a permission, so the GUI cannot call anything without it.

`API_IP_ADDRESS.txt` in that same directory is **tracked** in the GUI's repository, so `setup` checks it and reports rather than rewriting it.

### Individual commands

`setup` is the whole thing; these are the parts.

| Command | What it does |
| --- | --- |
| `clone` | Clone whatever is missing. The default. |
| `list` | What the registry declares, and whether it is present here. |
| `status` | Branch, uncommitted changes and drift from upstream, per repository. |
| `pull` | Fast-forward every clean repository. Skips any with uncommitted work. |
| `doctor` | Check the workspace is sound. Run this if anything looks wrong. |
| `db` | The database: `up`, `down`, `status`, `env`, `destroy`. |

Any command takes a single repository, named either as the registry calls it or as the directory is spelled — both are accepted because both are what you have in front of you:

```powershell
.\scripts\marp.ps1 clone marp-api
.\scripts\marp.ps1 status MARP_API
```

`VIDEO_PROCESSING_GUI` is private and needs credentials; the rest are public. `-Group components` skips the related repositories, and `--protocol ssh` clones over SSH.

### Which branch you get

A development workspace wants the branch work happens on, which is not always GitHub's default. `marp-api`'s default is `master`, roughly a year and 147 commits behind — with no `routes/` directory and no baseline schema, so a workspace cloned from it cannot even build its own database.

So the registry records the branch to develop on: `develop` for `marp-api`, `marp-inference-worker` and `video-processing-gui`. `marp-video-player` and `marp-jellyfin` have no `develop` branch at all and stay on `master`.

### Starting over

PostgreSQL lives inside the workspace, so it has to be stopped before the workspace can be deleted:

```powershell
.\scripts\marp.ps1 db down
```

`marp db destroy` deletes the database but keeps the PostgreSQL download, which is the quick way back to a clean database without re-downloading 330 MB.

### Linux and macOS

`scripts/marp.sh` covers `clone`, `list`, `status`, `pull`, `doctor` and `db`. `setup` is currently PowerShell only; on other platforms run `db up` and then `marp-api`'s own two commands, which the output tells you.

On Linux, `db up` uses the PostgreSQL you already have rather than downloading one — the PostgreSQL project publishes no portable Linux build — and prints the install command if there is none.

## Workspace layout

This repository is the workspace root. Each component is cloned as a subdirectory and remains its own independent Git repository, ignored by this one.

```text
MARP/                        this repository
├── MARP_API/                component repository
├── marp-jellyfin/           component repository
├── marp-video-player/       component repository
├── marp-inference-worker/   component repository
├── VIDEO_PROCESSING_GUI/    related repository
├── architecture/            system architecture and component boundaries
├── config/                  shared example configuration
├── deployment/              deployment definitions and orchestration
├── development/             developer setup and local-environment docs
├── services/                component registry and compatibility information
├── scripts/                 workspace management scripts
├── legacy/                  historical MARP prototype code
└── .postgres/               the local PostgreSQL, fetched on demand
```

`.postgres/` is git-ignored and holds both the server binaries and the database
itself — around 920 MB once `marp db up` has run. It is not committed, and
`marp db destroy` throws the database away.

### The umbrella never absorbs a component

Every component is a Git repository living inside this one. If a component directory stopped being ignored here, a commit in the umbrella would quietly pick up either that component's files or a gitlink pointing at it. Neither belongs in this repository's history, and both are awkward to undo later.

So the component directories are listed in `.gitignore`, and `scripts/marp doctor` verifies it rather than assuming it: every registered directory must be ignored, every present directory must be its own repository with the remote the registry expects, and the umbrella's working tree must show no component paths at all. `doctor` exits non-zero when any of that fails.

When a component is added, update `.gitignore` and `services/repos.yml` together, then run `doctor`.

## The database

`marp-api` cannot run without PostgreSQL, and until now the only development database was a hand-built server on a virtual machine — which a second machine cannot reproduce. `marp db up` closes that gap:

- Downloads a **self-contained PostgreSQL 18.6**. These are the official PostgreSQL binaries as published for Windows and macOS in plain archive form rather than wrapped in an installer: the same server, simply not registered with the operating system. Around 330 MB once, expanding to about 920 MB.
- No installer, **no administrator rights**, no virtual machine, no container runtime.
- Everything lives under `.postgres/`, which is git-ignored. `marp db destroy` deletes the database; deleting the directory removes every trace.
- Listens on **127.0.0.1 only**, on port 5432. If something is already there it stops and says so rather than quietly moving — pass `--port` (`-Port`) to place it elsewhere.

On Linux it uses the PostgreSQL you already have instead of downloading one, because the PostgreSQL project publishes no portable Linux build; if none is installed it prints the one-line command to install it.

**Production runs PostgreSQL 14 and this runs 18.** The baseline schema was captured from production and restores forward into 18 without complaint. The reverse is not true, so nothing built locally can be moved back to production without care — schema changes travel as migrations, which is the only route that works in both directions.

**The schema is not the umbrella's.** It belongs to `marp-api`, which carries the baseline and every migration, so `db up` finishes by running `marp-api`'s own commands against the new database. If `marp-api` is not cloned, not installed, or Node is not on `PATH`, it stops and prints those commands — a running database and honest instructions beat a silently half-finished one.

Nothing forces you to use it. `marp-api` connects through five `DB_*` variables and has no idea what is serving them, so pointing it at any other PostgreSQL is exactly as supported as it was before, and `db up` need never be run.

## Components and related repositories

`services/repos.yml` is the canonical registry. It separates two categories, because they are used differently.

**Components** make up a MARP deployment. These are what a MARP install consists of.

| Component | Repository | Runtime | Status |
| --- | --- | --- | --- |
| MARP API and application backend | `MARP_API` | Node 22, PostgreSQL | active |
| Video server (Jellyfin fork) | `marp-jellyfin` | .NET SDK | active |
| ML inference service | `marp-inference-worker` | Python 3.10+, NVIDIA GPU | active |
| Reusable video player | `marp-video-player` | Node 20+ | active |

`MARP_API` plus PostgreSQL is the smallest useful MARP install. The inference worker is optional.

**Related repositories** are developed alongside MARP but are not part of a MARP deployment. They are in this workspace so they can be maintained against the components they talk to.

| Repository | Runtime | Why it is here |
| --- | --- | --- |
| `VIDEO_PROCESSING_GUI` | .NET Framework 4.7.2, **Windows only** | Legacy desktop client that consumes the MARP API. Not part of the final system, but must be updated when the API changes. |

`marp-video-player` was extracted from `MARP_API` on 2026-08-31 and is now standalone, with its own build, tests, and docs. It is deliberately not a dependency of `MARP_API` — the two are disconnected.

It is published to npm, currently **0.4.0**, which is also the version bundled into `VIDEO_PROCESSING_GUI`. That GUI consumes it through a WebView2 host, so the `MarpVideoEngine` global, the `postMessage` protocol and `app/player.html`'s query parameters are a contract between two repositories and cannot change casually.

The API repository was renamed from `MARE_API` to `MARP_API`. GitHub still redirects the old name, which means a stale reference appears to work right up until somebody creates a new repository called `MARE_API`. Always use `MARP_API`.

## Status

What the umbrella provides today:

- The workspace layout and the component registry (`services/repos.yml`).
- `scripts/marp` — clone, list, status, pull, doctor.
- `scripts/marp db` — a PostgreSQL, provisioned and populated, with no installer or container runtime.
- `scripts/marp.ps1 setup` — a bare clone to a running database with a login and a GUI token, in one command.

What does not exist yet:

- **Nothing verifies a change in one component against another.** A `MARP_API` change that breaks the annotation GUI, or a player change that breaks its WebView2 host, is still found by hand. This is the largest remaining gap.
- No cross-component build or deployment definition.
- `setup` is PowerShell only. `scripts/marp.sh` covers everything else.
- `marp-jellyfin` cannot be built locally; it needs the .NET 9 SDK and currently runs on the development VM.

The `legacy/` directory is retained for reference. New platform-level work belongs in the appropriate top-level directory rather than in `legacy/`.
