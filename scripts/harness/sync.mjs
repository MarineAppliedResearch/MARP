/**
 * Keep every component's shared instruction block identical to the umbrella's.
 *
 * The alternative to this check is the thing it exists to prevent: four copies of the
 * platform rules that quietly disagree, which is exactly what `agents.md` had become
 * across this workspace before the harness existed.
 *
 * Usage:
 *   node sync.mjs           rewrite each component's shared block from AGENTS.md
 *   node sync.mjs --check    report drift and exit non-zero, changing nothing
 */

import { readFileSync, writeFileSync, existsSync, copyFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  UMBRELLA, HARNESS_DIR, SHARED_START, SHARED_END, BRAND_START, BRAND_END,
  sharedBlock, brandBlock, presentRepos, BRANDED,
  step, ok, fail, warn, dim, normalise,
} from './lib.mjs';

const check = process.argv.includes('--check');

let drifted = 0;
let missing = 0;
let written = 0;

/**
 * Rewrites one marked block in one file of every repository in `repos`, from the
 * umbrella's copy of it.
 *
 * Two blocks travel this way now and they are the same problem twice: the platform rules
 * in `AGENTS.md`, and the identity and cross-links in `README.md`. Both had already
 * diverged across this workspace before anything checked them.
 *
 * @param {object} spec what to sync.
 * @param {string} spec.title what the step line says.
 * @param {string} spec.file the file, relative to each repository root.
 * @param {string} spec.start the opening marker.
 * @param {string} spec.end the closing marker.
 * @param {string} spec.block the umbrella's copy, markers included.
 * @param {object[]} spec.repos the repositories to visit.
 * @param {string} spec.fix the command a failure should suggest.
 * @returns {void}
 */
function syncBlock({ title, file, start, end, block, repos, fix }) {
  step(check ? `Checking ${title}` : `Syncing ${title}`);

  for (const repo of repos) {
    const path = join(repo.path, file);
    const label = `${repo.name}/${file}`;

    if (!existsSync(path)) {
      // marp-jellyfin is deliberately outside the harness; anything else is a real gap.
      if (repo.name === 'marp-video-server') { warn(`${label} — outside the harness, skipped`); continue; }
      fail(`${label} — missing`);
      missing++;
      continue;
    }

    const text = readFileSync(path, 'utf8');
    const from = text.indexOf(start);
    const to = text.indexOf(end);

    if (from < 0 || to < 0) {
      fail(`${label} — no ${start} markers`);
      missing++;
      continue;
    }

    const current = text.slice(from, to + end.length);
    if (normalise(current) === normalise(block)) { ok(`${label} — in sync`); continue; }

    if (check) {
      fail(`${label} — drifted from the umbrella`);
      console.log(`         ${dim(`run: ${fix}`)}`);
      drifted++;
      continue;
    }

    writeFileSync(path, text.slice(0, from) + block + text.slice(to + end.length), 'utf8');
    ok(`${label} — rewritten`);
    written++;
  }
}

syncBlock({
  title: 'shared instruction blocks',
  file: 'AGENTS.md',
  start: SHARED_START,
  end: SHARED_END,
  block: sharedBlock(),
  repos: presentRepos(),
  fix: 'marp harness sync',
});

console.log('');

syncBlock({
  title: 'README brand blocks',
  file: 'README.md',
  start: BRAND_START,
  end: BRAND_END,
  block: brandBlock(),
  repos: BRANDED(),
  fix: 'marp harness sync',
});

console.log('');

/* The hook stub is the only harness code inside a component, and it is what lets a git
   worktree find the umbrella at all. A drifted copy means a worktree whose gates quietly
   do nothing, which is the failure this whole check exists to prevent. */
step(check ? 'Checking hook stubs' : 'Syncing hook stubs');

const canonical = normalise(readFileSync(join(HARNESS_DIR, 'hooks', 'stub.mjs'), 'utf8'));

for (const repo of presentRepos()) {
  if (repo.name === 'marp-video-server') continue;
  const path = join(repo.path, '.claude', 'hooks', 'gate.mjs');
  const label = `${repo.name}/.claude/hooks/gate.mjs`;

  if (existsSync(path) && normalise(readFileSync(path, 'utf8')) === canonical) {
    ok(`${label} — in sync`);
    continue;
  }
  if (check) {
    fail(`${label} — ${existsSync(path) ? 'drifted' : 'missing'}`);
    console.log(`         ${dim('run: marp harness install')}`);
    drifted++;
    continue;
  }
  copyFileSync(join(HARNESS_DIR, 'hooks', 'stub.mjs'), path);
  ok(`${label} — rewritten`);
  written++;
}

if (!check && written === 0) ok('nothing to do');

if (check && (drifted || missing)) {
  console.log('');
  fail(`${drifted} drifted, ${missing} missing or unmarked`);
  process.exit(1);
}
process.exit(missing && !check ? 1 : 0);
