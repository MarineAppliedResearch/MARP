---
task: MarineAppliedResearch/MARP#13
repos: [MARP, MARP_API, marp-video-player, VIDEO_PROCESSING_GUI]
status: design
needs: []
---

# Make the walkthrough tooling usable from every repository

## Goal

Anyone working on any MARP interface can record a narrated walkthrough of it, and a single
scripted tutorial can eventually span components — the mosaic reviewer, the video player,
and the annotation GUI in one film. Today only `marp-api` can, because the tooling lives
inside it.

## Requirements

- **R1** — `marp-video-player` can record a narrated walkthrough of its own player page.
- **R2** — `VIDEO_PROCESSING_GUI` can be included in a walkthrough, or it is written down
  why it cannot. It is a WPF desktop application, so Playwright drives it only through the
  WebView2 player page, if at all.
- **R3** — There is exactly one implementation of the recorder, the runner and the
  narration. Vendoring copies into each repository is the duplication this harness exists
  to prevent.
- **R4** — `marp-api` keeps working when cloned on its own, or the cost of it not doing so
  is accepted deliberately. It is a public repository that outside users clone standalone.
- **R5** — A tutorial can drive more than one component in one recording.

## Open assumptions

- [ ] **A1 · architectural · blocking** — Where does the shared tooling live? Three options,
      and they trade off differently:

      **(a) The umbrella, at `MARP/tools/walkthrough/`.** Components reference it by
      relative path, exactly as `.claude/settings.json` already references
      `../scripts/harness/hooks/`. No new repository, no npm, works today. Cost: recording
      a walkthrough requires the full workspace, so a standalone clone of `marp-api` or
      `marp-video-player` loses the ability — which breaks R4 unless we accept it.

      **(b) Its own repository plus an npm package.** `marp-video-player` already publishes
      to npm through trusted publishing, so the path exists. Each repository depends on it
      normally and standalone clones keep working. Cost: a new repository in the org, a
      release process, and a version to keep in step across four consumers.

      **(c) Leave it in `marp-api` and have others depend on that.** Rejected: `marp-api`
      is the whole backend, and depending on it from the player would invert a dependency
      the platform deliberately keeps disconnected.

      My recommendation is **(a)** — the precedent exists, it works today, and walkthroughs
      are a development and review activity done by somebody who has the workspace. But
      (a) knowingly breaks R4, and whether that matters is a product judgement about
      outside users of the public repositories, not something to infer from the code.

- [ ] **A2 · product/UI · non-blocking** — Is a cross-component tutorial one recording that
      navigates between applications, or several recordings stitched together? The first
      needs every component running at once; the second needs a stitching step that does
      not exist yet.

- [ ] **A3 · behavioural · non-blocking** — `VIDEO_PROCESSING_GUI` is WPF. Playwright cannot
      drive it. Is filming its embedded player page enough for R2, or does the desktop
      client need a different capture approach entirely?

## Decisions

- **2026-09-05** — `settled` is a callback rather than shared code, because knowing when a
  page has stopped moving cannot be guessed by a module that has never seen the page.
  Confirmed by a second consumer needing something completely different.
- **2026-09-05** — Playwright's `test` and `expect` are passed in, never imported by the
  shared module. It only registers a test when it is the same module instance the runner
  loaded, and each application installs its own.
- **2026-09-05** — Credentials for a walkthrough come from the environment. A recorded
  sign-in is exactly where a password would otherwise reach a tracked file.

## Plan

Blocked on A1. Once it is answered:

1. Move the tooling to wherever A1 says, keeping the current interface.
2. Give `marp-video-player` a walkthrough scenario for its player page (R1).
3. Answer R2 for the GUI in writing, whichever way it goes.
4. Update ADR-0007 with what was decided and why.

## Acceptance criteria

- A narrated walkthrough recorded from `marp-video-player`, watched and accepted.
- `marp-api`'s existing walkthroughs still record, unchanged.
- One implementation. `marp harness check` still passes.

## Test plan

Filled in at G3, after A1 is answered. The walkthroughs themselves are the evidence here,
which is unusual and worth stating: for this task the artifact and the verification are the
same recording.

## Status

- **Gate:** design — blocked at G1 on A1
- **Notes:** the extraction within `marp-api` is done and validated by a second consumer
  (ADR-0007). This task is only about reaching the other repositories.
