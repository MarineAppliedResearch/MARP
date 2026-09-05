# The contracts between MARP repositories

Every component is its own repository, so a change spanning two of them is two branches,
two pull requests and two merges. These are the places where a change on one side can break
the other, and what detects it.

Keep this file current. It is short on purpose — a contract that is not written here is one
nobody will remember to check.

## The coupling points

| Between | The contract | What detects a break |
| --- | --- | --- |
| marp-api → video-processing-gui | the HTTP API surface | `docs/openapi.generated.json` is committed and CI reports its diff against the merge base. **Advisory only** — nothing fails, and nothing tests the GUI against a changed API. |
| marp-video-player → video-processing-gui | the `MarpVideoEngine` global, the `postMessage` protocol, `app/player.html`'s query parameters | `test/e2e/host-contract.spec.js` in marp-video-player, from that side only |
| marp-api → marp-video-server | the Jellyfin API | nothing |
| marp-inference-worker → a future coordinator | standardised detection results | nothing; the coordinator does not exist yet |

**Two of the four have no detection at all.** That is the honest state, and it is the gap
worth closing next.

## Add, never change

marp-video-player's rule, and it generalises to every row above:

> New information goes out as a further field or a further message. Nothing that already
> goes out changes shape.

The reason is concrete. `MareMediaElement.xaml.cs` in video-processing-gui splits
`metadata|` and `frame|` on a fixed field count, so an extra field there breaks a host in a
repository you cannot see from the player. `HandleStatusMessage` matches known prefixes and
logs anything else, so a new `status|` line is free. That asymmetry is why the audio state
shipped as `status|audio …` rather than as fields on `metadata|`.

The same shape applies to the API: adding a route or an optional field is safe; removing a
path, renaming a field, or making an optional field required is a breaking change for a
consumer that cannot be tested from here.

## Versioning

marp-video-player is semver, with one rule: **a major bump means the host contract
changed**. A consumer relies on that to take a minor update without re-verifying its host.

marp-api versions its routes in the path. `routes/lib/register-versioned-route.js` registers
a route declared with its old V1 path once, at `/api/v2/...`, behind `requirePermission`.
There are no V1 routes.

## Working across two repositories

One `.marp/task.md`, listing both in `repos:`, not two specifications. The contract is
settled once, at gate G1, before either side is implemented — two agents each settling the
same contract independently is exactly how two incompatible interpretations get built.

A tracking issue in this umbrella references the component issues as
`MarineAppliedResearch/<repo>#<n>`.

Implementation can then fan out per repository, because by that point the interface is not
a question any more.

## What is not a contract

video-processing-gui is **not** part of MARP. It consumes the API and the player, and it is
in the workspace so it can be updated when they change. Nothing in MARP may depend on it.

marp-video-player is deliberately **not** consumed by marp-api. The two are disconnected,
and that is a decision rather than an oversight.
