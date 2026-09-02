# MARP Development Environment

This directory documents how to obtain and run the MARP ecosystem for development.

The model is a polyrepo workspace: each major MARP component remains its own Git repository, while this repository provides the shared setup and integration layer.

## Getting the code

Clone the umbrella, then let it fetch the rest:

```powershell
git clone https://github.com/MarineAppliedResearch/MARP.git
cd MARP
.\scripts\marp.ps1 clone
```

```bash
git clone https://github.com/MarineAppliedResearch/MARP.git
cd MARP
sh scripts/marp.sh clone
```

`services/repos.yml` decides what gets cloned and where. `scripts/marp doctor` checks the result. See `scripts/README.md` for the full command set.

`VIDEO_PROCESSING_GUI` is private, so cloning it needs credentials on the account; every other repository is public. It is also Windows-only and is not part of a MARP deployment — `--group components` skips it and the rest of the `related` category.

## Keeping it current

```powershell
.\scripts\marp.ps1 status    # what is checked out, what is dirty, what has drifted
.\scripts\marp.ps1 pull      # fast-forward everything that is clean
```

`pull` skips any repository with uncommitted work rather than risking it, so a clean report from `status` is worth checking first.

## Working across components

Each component is its own repository, so a change spanning two of them is two branches, two pull requests and two merges. Open a tracking issue in `MARP` and reference the component issues from it.

Nothing currently verifies that a change in one component still works against another. That gap is known.

## Per-component setup

Build and run instructions belong to each component and live in its own repository. This directory covers only what is shared across the workspace.
