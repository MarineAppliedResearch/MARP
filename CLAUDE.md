# MARP workspace

This is the workspace root for the MARP ecosystem. Each subdirectory listed below is an independent Git repository. Work here when a change spans more than one component.

`services/repos.yml` is the canonical registry. This file is the operational companion: how to build, run, and test each part, and what currently does not work.

## Conventions

These apply to every repository in this workspace.

- **Commit authorship is Isaac only.** Never add Claude as author or co-author, and never add a `Co-Authored-By` trailer. This applies to merge and squash commits too.
- **Keep commit messages short.** A subject line under ~72 characters plus a few one-line bullets. Reference the issue with `Refs #NN`.
- **Issues live where the code changes.** Cross-repo work gets a tracking issue in the `MARP` repo, referencing component issues as `MarineAppliedResearch/<repo>#<n>`.
- **Never commit `.env` files or credentials.** Each component has a `.env.example` where applicable.
- Component repositories keep their own `agents.md` / `CLAUDE.md` for specifics. This file holds only what is shared.

## Components

### marp-api — `MARE_API/`

The MARP API and application backend. Also serves the browser applications from `frontend/apps/`, including the video player.

- **Runtime:** Node 22.22.1, pinned in `.nvmrc`. Installed via nvm-windows at `C:\nvm4w\nodejs`.
- **Database:** development PostgreSQL runs on the Ubuntu VirtualBox VM `MARP DEV ENVIRONMENT`, reached at `localhost:5433` through a NAT port forward. Database `mare_v1`, role `mare_user`.
- **Config:** `.env` in the repo root, git-ignored. `.env.example` documents every variable.

```bash
cd MARE_API
npm install
npm run dev                      # nodemon, or press F5 in VS Code
npm test                         # 22 suites, 142 tests
npm run test:video-engine:unit   # 12 suites, 140 tests
npm run build:video-engine
npx sequelize-cli db:migrate:status
```

Serves `http://localhost:3000/`, `/api-docs`, `/developer-docs`.

### The video player — `MARE_API/video-engine/`

Not yet its own repository. Extraction is tracked in `MARP#1`.

Source in `video-engine/src/`, built with esbuild to `frontend/apps/VideoPlayer/dist/`. Unit tests use a separate Jest config at `video-engine/jest.config.js` with an esbuild transform, because the source is ES modules while the API suite is CommonJS. The root Jest config is scoped to `tests/` so the two do not collide.

The C# WebView2 host in `VIDEO_PROCESSING_GUI` consumes this player. See `MARE_API/docs/developer/csharp-host-integration.md`. Changing the host-facing contract affects that project.

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

The API and the player are the same repository today, so a change to both is one commit.

A change spanning the API and the GUI is two repositories and two commits. The coupling points are the HTTP API surface and the WebView2 player contract. Nothing currently detects when an API change breaks the GUI — that gap is known and untracked.

## Known gaps

- `marp-jellyfin` cannot be built locally (needs .NET 9 SDK).
- `marp-inference-worker` virtualenv needs recreating.
- No cross-component build or test command exists; each component is built on its own.
- Nothing verifies the GUI still works against a changed API.

## Environment note

Node was installed via nvm-windows after VS Code was already running. If `node` is not found in a terminal or a launch configuration, fully quit and reopen VS Code so it picks up the updated `PATH`.
