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

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  UMBRELLA, SHARED_START, SHARED_END, sharedBlock, presentRepos,
  step, ok, fail, warn, dim, normalise,
} from './lib.mjs';

const check = process.argv.includes('--check');
const block = sharedBlock();

let drifted = 0;
let missing = 0;
let written = 0;

step(check ? 'Checking shared instruction blocks' : 'Syncing shared instruction blocks');

for (const repo of presentRepos()) {
  const path = join(repo.path, 'AGENTS.md');
  const label = `${repo.name}/AGENTS.md`;

  if (!existsSync(path)) {
    // marp-jellyfin is deliberately outside the harness; anything else is a real gap.
    if (repo.name === 'marp-video-server') { warn(`${label} — outside the harness, skipped`); continue; }
    fail(`${label} — missing`);
    missing++;
    continue;
  }

  const text = readFileSync(path, 'utf8');
  const from = text.indexOf(SHARED_START);
  const to = text.indexOf(SHARED_END);

  if (from < 0 || to < 0) {
    fail(`${label} — no marp:shared markers`);
    missing++;
    continue;
  }

  const current = text.slice(from, to + SHARED_END.length);
  if (normalise(current) === normalise(block)) { ok(`${label} — in sync`); continue; }

  if (check) {
    fail(`${label} — drifted from the umbrella`);
    console.log(`         ${dim('run: marp harness sync')}`);
    drifted++;
    continue;
  }

  writeFileSync(path, text.slice(0, from) + block + text.slice(to + SHARED_END.length), 'utf8');
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
