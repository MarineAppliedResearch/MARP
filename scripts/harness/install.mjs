/**
 * Install the harness adapter files into each component repository.
 *
 * Everything written here is thin: a pointer, a permission rule, a template. The content
 * lives in AGENTS.md and in the umbrella's checks, so this script is safe to re-run and
 * is how a repository is brought back into line after the shared rules change.
 *
 * It does not write AGENTS.md itself. That file has a repository-specific half which is
 * hand-written and valuable; `sync.mjs` maintains only its shared block.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, copyFileSync } from 'node:fs';
import { join } from 'node:path';
import { UMBRELLA, presentRepos, readRegistry, step, ok, warn } from './lib.mjs';

const write = (path, content) => {
  mkdirSync(join(path, '..'), { recursive: true });
  writeFileSync(path, content, 'utf8');
};

const SETTINGS = {
  permissions: {
    allow: [
      'Read(//**)', 'Glob(//**)', 'Grep(//**)',
      'Bash(git status:*)', 'Bash(git diff:*)', 'Bash(git log:*)', 'Bash(git branch:*)',
      'Bash(npm test:*)', 'Bash(npm run test:*)', 'Bash(npm run lint:*)',
    ],
    ask: ['Bash(git push:*)', 'Bash(gh pr create:*)'],
    deny: ['Read(./.env)', 'Read(./.marp/local/**)'],
  },
  hooks: {
    PreToolUse: [
      {
        // Gate G1. The script fails open when the umbrella is not beside this repository,
        // so a standalone clone is unaffected rather than broken.
        matcher: 'Edit|Write|MultiEdit|NotebookEdit',
        hooks: [{ type: 'command', command: 'node "$CLAUDE_PROJECT_DIR/../scripts/harness/hooks/spec-gate.mjs"' }],
      },
      {
        matcher: 'Bash',
        hooks: [{ type: 'command', command: 'node "$CLAUDE_PROJECT_DIR/../scripts/harness/hooks/danger-gate.mjs"' }],
      },
    ],
  },
};

const copilot = (repo) => `# GitHub Copilot — ${repo.name}

**Read [AGENTS.md](../AGENTS.md) first.** It is the single source for how to work in this
repository: the workflow and its gates, the rules that are not negotiable, how assumptions
are surfaced, and the testing doctrine. This file holds only what is specific to Copilot.

## Start from \`${repo.default_branch}\`, not the default branch

This repository's GitHub default branch is not necessarily the branch work happens on.
\`services/repos.yml\` in the umbrella records the branch to develop on, and for this
repository it is **\`${repo.default_branch}\`**.

In this platform \`master\` means *what is in production* and is promoted by hand, so it can
be far behind — marp-api's is around 147 commits and a year behind \`develop\`, with an older
architecture. A coding agent that starts from the default branch starts there.

## Path-specific rules

Rules that apply to one part of the tree live in \`.github/instructions/*.instructions.md\`
and apply automatically to the paths they name. Prefer adding one there over repeating a
rule in a review comment.

## Reviewing

Copilot code review is welcome on pull requests and is not a gate. It is good at the class
of problem our checks do not cover, and it does not know what MARP means by a session, an
observation, or a review — so treat its comments about meaning as questions rather than
findings.

## What not to do

- Do not open a pull request as the completion of a task. Pull request creation is gate G5
  in AGENTS.md and belongs to the human.
- Do not report a tier as passing that you did not run.
`;

const PR_TEMPLATE = `## What and why

<!-- One paragraph. What changes for the person using MARP. -->

## The specification

<!-- Link the issue, and note that .marp/task.md on this branch carries the requirements,
     the assumptions and how they were answered. Reviewing this diff includes reviewing
     what it was supposed to do. -->

- Issue:
- Assumptions answered:

## Verification

<!-- .marp/verification.md carries the plan that was reviewed and the results that were
     actually produced. Summarise here; do not restate it. -->

- Tiers run:
- Requirements with no test:
- Known gaps:

## Checklist

- [ ] \`.marp/task.md\` has no unanswered \`blocking\` assumption
- [ ] Every defect fixed here has a named test at a tier that can observe it
- [ ] Durable decisions promoted to \`docs/decisions/\` or the umbrella's \`architecture/decisions/\`
- [ ] Generated output rebuilt if the change touches what generates it
- [ ] No credential, host, port or machine-specific path added to a tracked file
`;

const registry = Object.fromEntries(readRegistry().map((r) => [r.directory, r]));

step('Installing harness adapters');

for (const repo of presentRepos()) {
  if (repo.name === 'marp-video-server') { warn(`${repo.name} — outside the harness (ADR-0006)`); continue; }

  const meta = registry[repo.directory] || { default_branch: 'develop' };
  const p = (...parts) => join(repo.path, ...parts);

  mkdirSync(p('.claude'), { recursive: true });
  mkdirSync(p('.github'), { recursive: true });
  mkdirSync(p('.marp'), { recursive: true });

  write(p('.claude', 'settings.json'), JSON.stringify(SETTINGS, null, 2) + '\n');
  write(p('.github', 'copilot-instructions.md'), copilot({ name: repo.name, default_branch: meta.default_branch }));
  write(p('.github', 'pull_request_template.md'), PR_TEMPLATE);

  for (const t of ['task.template.md', 'verification.template.md']) {
    copyFileSync(join(UMBRELLA, '.marp', t), p('.marp', t));
  }

  // The task spec and the local notes are per-branch and per-machine; neither belongs in
  // a component's history beyond the branch that owns it.
  const gitignore = p('.gitignore');
  const existing = existsSync(gitignore) ? readFileSync(gitignore, 'utf8') : '';
  if (!existing.includes('.marp/local')) {
    writeFileSync(gitignore, existing.replace(/\s*$/, '\n') +
      '\n# --- Harness: machine-specific operational notes ---\n' +
      '# Hosts, accounts and key paths for one developer. Repository files may say that a\n' +
      '# credential exists and where it lives, never its value.\n' +
      '.marp/local/\n', 'utf8');
  }

  ok(`${repo.name} — settings, copilot instructions, PR template, .marp templates`);
}
