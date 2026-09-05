# ADR-0007 — Narrated walkthrough tooling becomes shared

- **Status:** accepted and implemented
- **Date:** 2026-09-05
- **Scope:** marp-api and the applications it serves
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

The stated goal is that this serves all of MARP's user interfaces, and eventually produces
a scripted video tutorial of the system.

**Scope, corrected 2026-09-05.** An earlier draft of this record read that as
*cross-repository* and proposed publishing the tooling as a package so `marp-video-player`
and `video-processing-gui` could consume it. That was an inference, and it was wrong.
`marp-api` serves the MARP applications from `frontend/apps/`, and that is the audience:
the tooling lives there and serves them. The video player and the annotation GUI have
their own test arrangements and are not consumers of this.

## Decision

The tooling is extracted from the mosaic reviewer into `marp-api/tools/walkthrough/`, so
every application `marp-api` serves can use it and a tutorial can span those applications. The scenario format, the
caption/say/act contract, the measure-then-hold timing, and the graceful degradation when
no speech engine is present all carry over unchanged.

Two constraints are part of the decision. It is **development tooling**: nothing in an
application or the API may depend on it, and it must never be the reason a build fails.
And it is **recorded when asked**, not as part of the development loop — the fast tiers run
after every change; videos are produced on request.

## Consequences

One implementation to maintain instead of one per application.

Done: `marp-api/tools/walkthrough/` holds the recorder, the runner and the narration, and
the mosaic reviewer consumes them through two small files. Verified by recording a
walkthrough through the extracted path. Two things had to change in the move -- `settled`
became a callback, because knowing when a page has stopped moving cannot be guessed from
shared code; and `test`/`expect` are passed in rather than imported, because Playwright
only registers a test when it is the same module instance the runner loaded, and each
application installs its own.

**Validated by a second consumer, 2026-09-05.** A platform-level walkthrough — the entry
page, scrolling its sections, opening the login dialog, signing in for real, and landing on
the dashboard — was built against the extracted tooling and recorded end to end. It needed
two files: a scenarios file and a six-line spec. That is the test that mattered, because
one consumer proves nothing about whether a thing is actually shareable.

Three things it confirmed:

- `settled` being a callback was necessary, not defensive. The mosaic reviewer waits for
  tiles with no skeletons; the entry page waits for `networkidle`. Shared code could not
  have guessed either.
- The refusal to write a video when the run fails is load-bearing. The first attempt failed
  on a missing browser binary and produced no file, rather than a partial recording.
- A scene that claims something must assert it. The sign-in scene asserts the URL actually
  became `/apps/dashboard`, so a broken login cannot produce a convincing film of a
  working one.

Credentials for such a walkthrough come from the environment, never from the scenario file —
`marp harness check` fails on a credential in a tracked file, and a recorded sign-in is
exactly where one would otherwise get committed.

Nothing further is required. `marp-api` is where the applications are served from, so it is
where the tooling belongs, and both current consumers reach it by relative path with no
packaging step, no version to keep in step, and no second copy.
