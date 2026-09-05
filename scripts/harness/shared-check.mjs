/**
 * Check one repository's shared instruction block against the umbrella's, by path.
 *
 * `sync.mjs --check` walks the registry, which is right in a full workspace and useless in
 * CI, where one component is checked out beside the umbrella and nothing else is.
 *
 *   node shared-check.mjs <dir> [<dir>...]
 */

import { readFileSync, existsSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { SHARED_START, SHARED_END, sharedBlock, step, ok, fail, dim, normalise } from './lib.mjs';

const dirs = process.argv.slice(2).filter((a) => !a.startsWith('--'));
if (!dirs.length) {
  console.error('usage: shared-check.mjs <dir> [<dir>...]');
  process.exit(2);
}

const block = normalise(sharedBlock());
let bad = 0;

step('Checking shared instruction blocks');

for (const dir of dirs) {
  const path = join(resolve(dir), 'AGENTS.md');
  const label = `${basename(resolve(dir))}/AGENTS.md`;

  if (!existsSync(path)) { fail(`${label} — missing`); bad++; continue; }

  const text = readFileSync(path, 'utf8');
  const from = text.indexOf(SHARED_START);
  const to = text.indexOf(SHARED_END);
  if (from < 0 || to < 0) { fail(`${label} — no marp:shared markers`); bad++; continue; }

  if (normalise(text.slice(from, to + SHARED_END.length)) === block) { ok(`${label} — in sync`); continue; }

  fail(`${label} — drifted from the umbrella`);
  console.log(`         ${dim('the shared block is edited in MARP/AGENTS.md, then: marp harness sync')}`);
  bad++;
}

process.exit(bad ? 1 : 0);
