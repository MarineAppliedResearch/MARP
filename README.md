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

## Components

`services/repos.yml` is the canonical registry, including the runtime each component needs. Summary:

| Component | Repository | Runtime | Status |
| --- | --- | --- | --- |
| MARP API and application backend | `MARE_API` | Node 22, PostgreSQL | active |
| Video server (Jellyfin fork) | `marp-jellyfin` | .NET SDK | active |
| ML inference service | `marp-inference-worker` | Python 3.10+, NVIDIA GPU | active |
| Desktop annotation client | `VIDEO_PROCESSING_GUI` | .NET Framework 4.7.2, Windows only | transition |
| Reusable video player | not extracted | Node | undecided |
| `marp-web` | does not exist | unknown | undecided |

Two entries are deliberately marked undecided rather than planned. The video player currently lives inside `MARE_API/video-engine/`, and `marp-web`'s purpose has not been settled. See `services/repos.yml` for the detail.

## Status

The umbrella currently provides the workspace layout and the component registry. Bootstrap tooling under `scripts/` does not exist yet, and no cross-component build or deployment definition exists. Those are open work.

The `legacy/` directory is retained for reference. New platform-level work belongs in the appropriate top-level directory rather than in `legacy/`.
