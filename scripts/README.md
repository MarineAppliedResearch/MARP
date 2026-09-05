# MARP Platform Scripts

Scripts for working across the MARP repositories.

## marp — workspace management

`marp.ps1` (Windows) and `marp.sh` (Linux and macOS) are the same tool. They read `services/repos.yml` and manage every component repository in the workspace.

```powershell
.\scripts\marp.ps1 clone
.\scripts\marp.ps1 status
.\scripts\marp.ps1 doctor
```

```bash
sh scripts/marp.sh clone
sh scripts/marp.sh status
sh scripts/marp.sh doctor
```

| Command | What it does |
| --- | --- |
| `list` | What the registry declares, and whether it is present here. The default, because it is the only command that cannot surprise you. |
| `clone` | Clone whatever is missing, at the registered default branch. Skips what is already there and refuses to write into a directory it did not create. |
| `status` | Branch, uncommitted change count and drift from upstream, per repository. |
| `pull` | Fast-forward every clean repository. Skips any with uncommitted work rather than risking it. |
| `doctor` | Check the workspace is sound. Exits non-zero on any failure, so it works in CI or a hook. |

Options are `-Group` / `--group` (`all`, `components`, `related`) and `-Protocol` / `--protocol` (`https`, `ssh`). PowerShell help is available with `Get-Help .\scripts\marp.ps1 -Full`; the shell version takes `--help`.

### What doctor checks

- Git is on `PATH`.
- The registry is readable, and every entry has a directory and a default branch.
- **Every registered directory is ignored by the umbrella.** This is the check that matters most — see the README's note on why the umbrella must never absorb a component.
- Every present directory is its own Git repository, with the remote the registry expects.
- No component is still sitting under a former directory name.
- The umbrella's working tree shows no component paths.

## Adding a component

1. Add it to `services/repos.yml` with a `repository`, `directory`, `default_branch` and `visibility`.
2. Add `/<directory>/` to the umbrella `.gitignore`.
3. Run `doctor`. It fails if those two disagree.

There is nothing to change in the scripts themselves — the registry is the source of truth, and that is deliberate.

## A note on the registry parser

Neither script uses a YAML library. Requiring one before the workspace exists would defeat the point of a bootstrap script, so both parse the constrained shape documented in `services/repos.yml`'s own header: group keys at column 0, a repository key at two spaces, its fields at four, folded values at six or more.

That is a real constraint on how the registry may be written, and it is why `doctor` fails when it reads no entries: a registry edit that breaks the shape shows up as a check failure rather than as a silently skipped repository.

## harness, spec, verify, worktree — the agentic development harness

`marp harness|spec|verify|worktree` delegate to `scripts/harness/`, which is Node rather
than another pair of shell scripts: these commands parse Markdown and JSON, which is fine
in Node and miserable in sh. Node missing from `PATH` is reported the way `db` reports it.

```powershell
.\scripts\marp.ps1 harness check        # shared blocks, instruction files, the gates
.\scripts\marp.ps1 spec check MARP_API  # gate G1 -- is the design settled?
.\scripts\marp.ps1 verify plan MARP_API # gate G3 -- the test plan, and what has no test
.\scripts\marp.ps1 worktree marp-api 71-something
```

`AGENTS.md` in the umbrella is the source for the rules these enforce. The design and the
reasoning behind it are in `architecture/decisions/` and in
[MARP#13](https://github.com/MarineAppliedResearch/MARP/issues/13).

Two of these are worth knowing about:

- **`harness check` runs `self-test.mjs`**, which asserts that the Claude Code hooks
  actually deny what they are supposed to deny. Both hooks fail open by design, in several
  situations, which makes "always allows" an easy state to reach by accident — and a gate
  that always allows is indistinguishable from no gate.
- **`doc-check.mjs` fails on a host or port written into an instruction file.** That is
  deliberate and it is the rule in ADR-0005: point at the command that prints the value,
  because a value in prose goes stale silently.
