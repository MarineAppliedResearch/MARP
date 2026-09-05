# MARP — agent instructions

This is the tool-neutral source. Claude Code, Codex/ChatGPT and GitHub Copilot all read
the same rules from here; `CLAUDE.md` and `.github/copilot-instructions.md` are pointers
to this file plus whatever is genuinely specific to one tool.

Every component repository carries a copy of the shared block below, between the same two
markers, followed by its own repository-specific section. `marp harness check` fails when
a copy has drifted; `marp harness sync` rewrites them from this file.

<!-- marp:shared start -->
<!-- Canonical source: MARP/AGENTS.md. Do not edit this block in a component repository;
     edit it here and run `marp harness sync`. -->

## The platform

MARP is a polyrepo. `services/repos.yml` in the umbrella repository is the registry of
what MARP consists of, and it is authoritative — including for which branch to work on.

**Start from `repos.yml`'s `default_branch`, not from GitHub's default branch.** They
differ deliberately. `master` in this platform means *what is in production*, and
production is promoted by hand, so `master` can be far behind and that is not decay. Work
happens on `develop` where a repository has one.

Branch model is Gitflow: `master` is production, `develop` is integration, and every task
gets its own branch off `develop` named for its issue (`68-mosaic-review-prototype`).
Never commit directly to `master` or `develop`.

## Rules that are not negotiable

- **Commit authorship is the human developer only.** Never add an AI assistant as author
  or co-author, never add a `Co-Authored-By` trailer, and never mention an assistant or
  vendor in a commit message, PR title, or PR body. This applies to merge and squash
  commits too.
- **Never commit `.env` files, credentials, tokens, keys, or host passwords.** Each
  repository has a `.env.example` documenting variable *names*. Operational detail for a
  specific machine goes in `.marp/local/`, which is git-ignored.
- **The production database is a scientific record.** `mare_v1` holds years of annotation
  that is queried and reported on by people and tools outside this workspace. Any
  transformation of existing data must either preserve everything currently possible or
  lose nothing — a column that stops being populated, a value that becomes ambiguous, or a
  format an existing query no longer parses all count as loss, even when the application
  still works. Derived columns are part of the contract.
- **Ask about meaning rather than inferring it from the data.** How a field is meant to
  work, what an empty value means, whether two similar rows are one thing or two — these
  are answerable by the person who recorded them and not reliably by inspection.

## Keep commit messages short

Subject under ~72 characters plus a few one-line bullets. Reference the issue with
`Refs #NN` or `Closes #NN`. Cross-repository work references the other side in full:
`MarineAppliedResearch/MARP_API#68`.

## The workflow, and where it stops for a human

```
G0  Intake      read the task, this file, and the repository's decision records
G1  Design      investigate -> write .marp/task.md -> surface assumptions
    GATE          the human answers. Nothing is implemented while a `blocking`
                  assumption is open. This is enforced, not requested.
G2  Implement   implement the settled spec. Fast, autonomous, no questions --
                  unless a NEW material assumption appears, which returns to G1.
G3  Test plan   write .marp/verification.md: what will be tested, which
    GATE          requirement each test proves, and what is NOT covered.
                  The human reviews the PLAN before anything is run.
G4  Verify      run the approved verification, record real results including
    GATE          failures, verbatim. The human reviews the evidence.
G5  PR          opened only when the human says so. Never automatically.
G6  Merge       CI green plus human approval.
```

`.marp/task.md` is the task specification and it lives on the task's own branch, so it
travels with the code and appears in the pull request. `.marp/task.template.md` is the
skeleton. Durable decisions are promoted out of it into decision records
(`docs/decisions/` for one repository, the umbrella's `architecture/decisions/` for
anything spanning two).

## Surfacing assumptions is the point

Agents make plausible but incorrect assumptions, and a material assumption must never
silently become an implementation decision. During G1, write down anything of these kinds
that the task does not settle:

behavioural · product/UI · scientific or data-meaning · database/schema · API contract ·
architectural · performance/concurrency · security/permissions · destructive operations ·
cross-repository integration · environment

Each goes in `## Open assumptions` in `.marp/task.md` as a checklist item tagged with its
category and whether it is `blocking`. `marp spec check` fails while a blocking assumption
is unticked, which is what actually stops G2 from starting.

Trivial local choices that follow an established pattern in the repository are not
assumptions. If you are unsure whether something is material, the test is: *would a
different reasonable answer change the behaviour, the schema, the interface, or the
data?* If yes, it is material.

Discovering a new material assumption during G2 is normal and is not a failure. Append it,
say so, and stop — do not guess to preserve momentum.

## Working in parallel

Several agents can work at once, and the model is the ordinary one: **each works on its own
branch, in its own copy of the repository, and pushes that branch when the work is done.**
Branches are merged the usual way. The only extra requirement is that two agents must not
collide over the things a running MARP needs.

```bash
marp agent start marp-api 71-thumbnail-lifecycle
```

That gives the branch its own copy, its own database on its own port, its own API port, a
written `.env`, and its dependencies installed — so it can run and test without touching
anybody else's. `marp agent list` shows what is set up and where; `marp agent env <branch>`
prints the settings again; `marp agent remove <branch>` throws the copy away and **keeps
the branch**, because tidying up and discarding work should never be the same command.

On a second machine there is nothing to set up: clone the repository, check out the branch,
and it is already isolated. The command exists for putting several on one machine.

Two things are deliberately shared:

- **Jellyfin.** Every agent talks to the central MARP media server. It holds the real
  library, and the tests that touch it read far more than they write. A task that genuinely
  needs its own instance says so; nothing else should.
- **The PostgreSQL binaries**, downloaded once. Only the data directory is per-agent.

**Parallelism comes after the design is settled, never before.** Two agents each doing
their own investigation on overlapping surface is how two incompatible interpretations of
MARP get built. One agent settles the assumptions with the human; then the work fans out.

## Testing doctrine

Learned the expensive way, and it holds everywhere in this platform:

- **A defect is not fixed until it has a named test at a tier that can actually observe
  it.** Several defects here were reported twice because the first fix was verified at a
  tier that structurally could not see the bug. Store-level checks cannot see what was
  drawn; unit tests cannot see what a browser rendered.
- **A test that narrates a result without asserting it can lie.** This applies to
  walkthrough videos especially: a scene that says "the tile is now excluded" and only
  asserts that a panel opened will pass for weeks while excluding nothing.
- **Run the fast tiers after every change.** Parse and unit checks cost about a second.
  Do not run slow browser, database or hardware suites for routine feedback; they belong
  to the person working, and to G4.
- **A skipped suite looks green.** Prerequisites missing should fail, not skip.

## Documentation that states an environment fact

**Point at the command; do not restate the value.** A host, a port, a path or a version
written into prose goes stale silently and an agent cannot tell. Write *"run `marp db
status` to see yours"* rather than naming a host and port.

This is not a style preference. The umbrella's own `CLAUDE.md` once described the database
in two contradictory ways sixty lines apart, and an agent resolved the contradiction toward
the stale half and built a plan on it. `marp harness check` now greps tracked instruction
files for environment literals and retired markers.

The same rule retires any document that promises to stay in sync with code it cannot
observe. Do not write a `## Current API` section by hand; point at the generated contract.

## How corrections become durable

When a human corrects an agent, the correction should make the same mistake less likely
next time. Route it by this ranking:

> **A correction becomes a check if it possibly can, a test if it cannot be a check, and a
> sentence only if it can be neither.**

| The correction is about | Where it goes |
| --- | --- |
| what the system should do | `.marp/task.md` requirements, plus a test naming that requirement |
| a decision that constrains future work | a decision record |
| how agents should work, everywhere | this shared block |
| a rule for one area of one tree | `.github/instructions/*.instructions.md` |
| a defect | a named test at the tier that can see it |
| a mechanically checkable invariant | `marp doctor` or `marp harness check` or CI |
| something an agent should not do | a hook or a permission rule |

## Permissions

**Free:** read anything, search, run parse/unit/contract tiers, write to a task branch,
write `.marp/*`, commit locally, query a local disposable database, read the GitHub API.

**Ask first:** `git push` · opening a pull request (this is gate G5) · migrations against
anything but a local disposable database · any write to a shared database · adding a
dependency · editing generated output by hand · changing a published contract surface.

**Never without the human present:** anything against production `mare_v1` · the live
Jellyfin service and its configuration · force push · branch deletion · rewriting
published history · restoring anything from a `retired-migrations` directory · rotating
credentials.

## Working style

The human is the programmer; the agent is the assistant.

- Do not race ahead, and do not design large systems without checking direction.
- Work one milestone at a time. If asked for a test, give exactly that test and wait for
  the result before moving on.
- If a failure is reported, focus on that failure. Do not pile on unrelated improvements.
- **Report a failure the moment you see it.** Do not silently run diagnostics while
  somebody waits, and never present a partial result as a finished one.
- State assumptions explicitly. If several interpretations exist, present them rather than
  picking silently. If a simpler approach exists, say so.
- Minimum code that solves the problem. No speculative features, no abstractions for
  single-use code, no configurability that was not asked for.
- Touch only what the task requires. Do not reformat, refactor or "improve" adjacent code.
  Match the existing style even where you would do it differently. Remove only the imports
  and variables your own change orphaned.
- Comments: many short ones rather than a few long ones, about two lines on average, and
  they explain *why* far more than *what*.

<!-- marp:shared end -->

## This repository

The umbrella. It holds no application code — it is the registry, the cross-repository
documentation, and the tooling that manages the workspace.

```
services/repos.yml        the registry. Authoritative, and read by the scripts.
scripts/marp.{ps1,sh}     clone, status, pull, doctor, db, spec, verify, worktree, harness
scripts/harness/          the checks, in Node. One implementation, several callers.
architecture/decisions/   cross-repository ADRs
architecture/contracts.md the coupling points between repositories
.marp/                    task and verification templates; local/ is git-ignored
```

**The umbrella never absorbs a component.** Every component directory is git-ignored here
and `marp doctor` fails if the registry and `.gitignore` disagree. Adding a component means
editing `services/repos.yml` and `.gitignore`, not editing the scripts.

**The database.** `marp db up` produces a self-contained PostgreSQL for development —
no installer, no administrator rights, no VM, no container. `marp db status` reports where
yours is listening; `marp db env` prints the `DB_*` settings marp-api needs. `.env` is
printed, never written, because that file also holds other credentials. `marp db destroy`
throws it away.

The schema belongs to marp-api, which holds the baseline and the migrations; `db up` runs
marp-api's own scripts rather than keeping a second copy that would drift. marp-api never
learns where its database came from — it reads five `DB_*` variables and has no idea what
is serving them.

Node not being on `PATH` is a routine state on a fresh Windows shell, not a broken machine.
The nvm symlink is at `C:/nvm4w/nodejs`.
