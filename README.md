# MARP Platform

MARP (Marine Analysis and Reporting Platform) is composed of multiple independently maintained applications and services. This repository is the umbrella repository for the MARP ecosystem: architecture, deployment, development setup, compatibility information, and system-level documentation.

## Core repositories

- `MarineAppliedResearch/marp-web` — browser application
- `MarineAppliedResearch/MARE_API` — MARP scientific/data API (planned rename: `marp-api`)
- `MarineAppliedResearch/marp-video-player` — reusable JavaScript/WebCodecs video player
- `MarineAppliedResearch/marp-jellyfin` — MARP video server, forked from Jellyfin (planned rename: `marp-video-server`)
- `MarineAppliedResearch/marp-inference-worker` — ML inference service
- `MarineAppliedResearch/VIDEO_PROCESSING_GUI` — legacy/transition desktop client consuming MARP components

## Repository layout

- `architecture/` — system architecture and component boundaries
- `config/` — shared example configuration and environment definitions
- `deployment/` — deployment definitions and orchestration
- `development/` — developer setup and local-environment documentation
- `services/` — service registry and compatibility/version information
- `scripts/` — bootstrap and ecosystem-management scripts
- `legacy/` — historical MARP prototype code that previously lived at the repository root

The `legacy/` directory is retained for reference. New platform-level work should be placed in the appropriate top-level directory rather than added to `legacy/`.
