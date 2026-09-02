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
.\scripts\marp.ps1 clone
```

```bash
# Linux and macOS
sh scripts/marp.sh clone
```

Then open `marp.code-workspace` for a multi-root VS Code window over every repository at once.

`clone` skips anything already present and never writes into a directory it did not create, so it is safe to re-run. `VIDEO_PROCESSING_GUI` is private and needs credentials; the rest are public. Add `--group components` (`-Group components` in PowerShell) to skip the related repositories, or `--protocol ssh` to clone over SSH.

Other commands:

| Command | What it does |
| --- | --- |
| `list` | What the registry declares, and whether it is present here. The default. |
| `clone` | Clone whatever is missing. |
| `status` | Branch, uncommitted changes and drift from upstream, per repository. |
| `pull` | Fast-forward every clean repository. Skips any with uncommitted work. |
| `doctor` | Check the workspace is sound. Run this if anything looks wrong. |

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
