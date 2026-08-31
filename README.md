# MARP Platform

MARP (Marine Analysis and Reporting Platform) is composed of multiple independently maintained applications and services. This repository is the umbrella repository for the MARP ecosystem: it is the workspace root, and it holds architecture, deployment, development setup, compatibility information, and system-level documentation.

The goal is a single system that builds easily and can be worked on as a whole, rather than a set of repositories that each have to be discovered and configured by hand.

## Workspace layout

This repository is the workspace root. Each component is cloned as a subdirectory and remains its own independent Git repository, ignored by this one.

```text
MARP/                        this repository
├── MARE_API/                component repository
├── marp-jellyfin/           component repository
├── marp-inference-worker/   component repository
├── VIDEO_PROCESSING_GUI/    component repository
├── architecture/            system architecture and component boundaries
├── config/                  shared example configuration
├── deployment/              deployment definitions and orchestration
├── development/             developer setup and local-environment docs
├── services/                component registry and compatibility information
├── scripts/                 bootstrap and ecosystem-management scripts
└── legacy/                  historical MARP prototype code
```

Component directories are listed in `.gitignore`. When a component is added, update both `.gitignore` and `services/repos.yml`.

## Components and related repositories

`services/repos.yml` is the canonical registry. It separates two categories, because they are used differently.

**Components** make up a MARP deployment. These are what a MARP install consists of.

| Component | Repository | Runtime | Status |
| --- | --- | --- | --- |
| MARP API and application backend | `MARE_API` | Node 22, PostgreSQL | active |
| Video server (Jellyfin fork) | `marp-jellyfin` | .NET SDK | active |
| ML inference service | `marp-inference-worker` | Python 3.10+, NVIDIA GPU | active |
| Reusable video player | not extracted | Node | undecided |
| `marp-web` | does not exist | unknown | undecided |

`MARE_API` plus PostgreSQL is the smallest useful MARP install. The inference worker is optional.

**Related repositories** are developed alongside MARP but are not part of a MARP deployment. They are in this workspace so they can be maintained against the components they talk to.

| Repository | Runtime | Why it is here |
| --- | --- | --- |
| `VIDEO_PROCESSING_GUI` | .NET Framework 4.7.2, **Windows only** | Legacy desktop client that consumes the MARP API. Not part of the final system, but must be updated when the API changes. |

Two component entries are deliberately marked undecided rather than planned. The video player currently lives inside `MARE_API/video-engine/`, and `marp-web`'s purpose has not been settled.

## Status

The umbrella currently provides the workspace layout and the component registry. Bootstrap tooling under `scripts/` does not exist yet, and no cross-component build or deployment definition exists. Those are open work.

The `legacy/` directory is retained for reference. New platform-level work belongs in the appropriate top-level directory rather than in `legacy/`.
