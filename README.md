# MARP Platform

MARP (Marine Analysis and Reporting Platform) is composed of multiple independently maintained applications and services. This repository is the umbrella repository for the MARP ecosystem: it is the workspace root, and it holds architecture, deployment, development setup, compatibility information, and system-level documentation.

The goal is a single system that builds easily and can be worked on as a whole, rather than a set of repositories that each have to be discovered and configured by hand.

## Getting the whole workspace

Clone this repository, then run one script. It reads `services/repos.yml` and clones every component into its own subdirectory, so everything is reachable from one place — by a person or by an agent — without merging any histories.

```bash
git clone https://github.com/MarineAppliedResearch/MARP.git
cd MARP
```

```powershell
# Windows
.\scripts\marp.ps1
```

```bash
# Linux and macOS
sh scripts/marp.sh
```

`clone` is the default, so a bare invocation fetches everything. Then get a database, which `marp-api` cannot run without:

```powershell
.\scripts\marp.ps1 db up
```

```bash
sh scripts/marp.sh db up
```

That downloads a self-contained PostgreSQL, starts it, and has `marp-api` load its schema — see [The database](#the-database). Finally, put the `DB_*` settings it prints into `MARP_API/.env`, and open `marp.code-workspace` for a multi-root VS Code window over every repository at once.

`clone` skips anything already present and never writes into a directory it did not create, so it is safe to re-run. `VIDEO_PROCESSING_GUI` is private and needs credentials; the rest are public. Add `--group components` (`-Group components` in PowerShell) to skip the related repositories, or `--protocol ssh` to clone over SSH.

Any command takes a single repository, named either as the registry calls it or as the directory is spelled — both are accepted because both are what you have in front of you:

```bash
sh scripts/marp.sh clone marp-api
sh scripts/marp.sh status MARP_API
```

Other commands:

| Command | What it does |
| --- | --- |
| `list` | What the registry declares, and whether it is present here. The default. |
| `clone` | Clone whatever is missing. |
| `status` | Branch, uncommitted changes and drift from upstream, per repository. |
| `pull` | Fast-forward every clean repository. Skips any with uncommitted work. |
| `doctor` | Check the workspace is sound. Run this if anything looks wrong. |
| `db` | Provision and run the PostgreSQL database. `up`, `down`, `status`, `env`, `destroy`. |

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
└── legacy/                  historical MARP prototype code
```

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

The API repository was renamed from `MARE_API` to `MARP_API`. GitHub still redirects the old name, which means a stale reference appears to work right up until somebody creates a new repository called `MARE_API`. Always use `MARP_API`.

## Status

The umbrella provides the workspace layout, the component registry, and the workspace management script under `scripts/`. No cross-component build or deployment definition exists yet, and nothing verifies that a change in one component still works against another. Those are open work.

The `legacy/` directory is retained for reference. New platform-level work belongs in the appropriate top-level directory rather than in `legacy/`.
