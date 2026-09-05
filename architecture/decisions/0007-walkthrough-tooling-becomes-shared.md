# ADR-0007 — Narrated walkthrough tooling becomes shared

- **Status:** accepted, not yet implemented
- **Date:** 2026-09-05
- **Scope:** marp-api, marp-video-player, video-processing-gui
- **Refs:** MarineAppliedResearch/MARP#13

## Context

`frontend/apps/marp-mosaic-review/` grew a walkthrough system: Playwright drives a scenario,
each narration line is spoken and *measured* before the run so scenes hold for exactly as
long as their own narration, and ffmpeg mixes the audio over the recording. A scenario file
is the whole interface; the runner and recorder need no changes to add one.

It has been the most effective review surface in the platform. Three defects were found by
a walkthrough that every automated tier passed. It also carries a hard-won rule: **a scene
that narrates a result and does not assert it can lie** — one scene passed for a week while
excluding nothing, because it only asserted that a panel had opened.

The stated goal is that this serves all UI work, and eventually produces a scripted video
tutorial covering the whole MARP system.

## Decision

The tooling is extracted from the mosaic reviewer so other applications and other
repositories can use it, and so a tutorial can span components. The scenario format, the
caption/say/act contract, the measure-then-hold timing, and the graceful degradation when
no speech engine is present all carry over unchanged.

Two constraints are part of the decision. It is **development tooling**: nothing in an
application or the API may depend on it, and it must never be the reason a build fails.
And it is **recorded when asked**, not as part of the development loop — the fast tiers run
after every change; videos are produced on request.

## Consequences

One implementation to maintain instead of one per application. Until the extraction is
done, the mosaic reviewer's copy remains the reference implementation and this record is
the statement of intent — the work itself is not yet started.
