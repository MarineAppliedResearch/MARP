# Running a task through the harness

How to take an idea and get it merged, using the agentic development harness. Written for
the person driving, not for the agent — the agent's copy of the rules is `AGENTS.md`.

The whole thing in one line: **you decide what and whether; the agent decides how, and
proves it.**

---

## Before anything: write the issue

In the repository the work belongs to. `MARP` only when the work spans two of them.

Three things, and no more:

- **The goal** — what changes for the person using MARP. Not what changes in the code.
- **What is already settled** — decisions you have made, so the agent does not reopen them.
- **What you already know is unclear** — optional. The agent will surface its own; this is
  for the ones you can see coming.

Do not write the implementation. If you already know the implementation, you are writing
a spec, and the agent will do it faster if you say so plainly instead.

## 1. Give the agent a workspace

```bash
marp agent start marp-api 71-delete-confirmation
```

It gets its own copy of the repository on that branch, its own database on its own port,
its own API port, a written `.env` and every package installed. It cannot collide with your
development server or with another agent.

Then point an agent at that directory and the issue. That is all the briefing it needs —
`AGENTS.md` is in there and tells it the rest.

> On a second computer none of this is needed. Clone, check out the branch, and it is
> already isolated. The command exists for running several on one machine.

## 2. Answer its questions — the gate that matters most

The agent investigates and writes `.marp/task.md`: the goal, numbered requirements, and
**every assumption it is making that you have not settled.** It cannot edit anything
outside `.marp/` until you have answered the ones marked `blocking`. That refusal is
enforced by a hook, not by good intentions.

Expect three to five real questions. On the first task through, they were: does confirming
a delete need typing, or is a click enough; every time or suppressible; should it warn
about already-reviewed records; how specific must the wording be. Every one of those
changed what got built.

**Answer in chat or in the issue.** You never have to edit the file. The agent folds your
answers in, with the reasoning attached, and the gate opens.

If it asks nothing, be suspicious.

## 3. It implements

No further input from you. This is the part that should be fast, and it is fast precisely
because the questions were asked first.

## 4. Review the test plan — before anything runs

The agent writes `.marp/verification.md` and stops. It says which test proves which
requirement, at which tier, **and which requirements have no test at all.**

This is where "you're missing this case" and "that test does not actually prove it" are
cheap. Once tests exist, saying so is expensive.

What to look for:

- **Is it testing at a tier that can see the thing?** A rule belongs in unit tests, "did it
  actually send" in the contract tier, anything on screen in the browser. Every rendering
  defect this project has had passed the store-level checks.
- **Are the gaps stated?** A plan with no "known gaps" section is a plan that has not been
  thought about.

## 5. Read the results, and watch the video

The agent runs the whole suite and appends the real output — failures verbatim, not
summarised. For anything with a user interface, ask for a narrated walkthrough:

```bash
npm run demo:narrated -- verify-delete-confirmation
```

Thirty seconds, and it asserts everything it narrates. If the feature is broken the run
fails and writes **no video**, rather than producing a convincing film of something that
does not work.

## 6. You say when it becomes a pull request

Nothing opens a PR on its own. Say so, or merge it yourself.

## 7. After it merges

```bash
marp spec retire marp-api          # the task spec dies with its branch
marp agent remove 71-delete-confirmation
```

`remove` shuts down that workspace's database and servers and deletes the copy. **It keeps
the branch** — tidying up and throwing work away should never be the same command.

`marp harness check` fails if a spec is left on `develop`, so forgetting is caught.

---

## Several agents at once

Parallelism belongs **after** the design is settled, never before. Two agents each
investigating the same surface is how two incompatible interpretations get built.

So: one agent settles the assumptions with you, then the work fans out. Each gets its own
`marp agent start`. `marp harness check` reports collisions — same port fails, an exclusive
resource named twice in `needs:` fails, two agents on one repository is a note for you.

**Subagents inside one task** are for reading, not writing: searching a large tree,
reviewing a diff against the requirements. Give a reviewer the requirements and the diff,
never the implementation transcript, or it inherits the reasoning that produced the bug.
Parallel *implementers* should be separate workspaces, because they need their own database
and their own branch.

## What runs when

| | |
| --- | --- |
| After every change | `npm run test:unit` — about a second |
| Every push | CI, fast tiers only |
| Before calling anything done | the whole suite, `marp verify run` |

**CI going green is not the same as verified.** CI runs the fast tiers deliberately; the
thorough run happens where somebody is already waiting to review it.

## When a correction is worth keeping

If you correct the same thing twice, it belongs somewhere durable:

> **A correction becomes a check if it possibly can, a test if it cannot be a check, and a
> sentence only if it can be neither.**

A sentence in an instruction file is the weakest artifact available, and is what most
projects use for everything.

## The commands

```bash
marp agent start <repo> <branch>   a branch that can run and test on its own
marp agent list                    what is set up, and on which ports
marp agent stop|remove <branch>    shut it down; remove keeps the branch

marp spec check [dir]              is the design settled? (the G1 gate)
marp spec retire [dir]             after merge

marp verify plan [dir]             the test plan, and what has no test
marp verify run [dir]              the whole suite, results recorded

marp harness check                 instructions, gates, specs, collisions
marp doctor                        the workspace, including all of the above
```
