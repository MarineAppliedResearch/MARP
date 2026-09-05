/**
 * A task specification must not sit on an integration branch.
 *
 * `.marp/task.md` belongs to one task and dies with its branch (ADR-0003). Merged onto
 * `develop` or `master` it reads as current: the next person to open it is looking at
 * somebody else's settled assumptions, and the G1 gate will hold or release their work
 * against the wrong questions.
 *
 * This was found by hand -- the first task through the harness merged its spec onto
 * develop and nothing noticed.
 *
 *   node spec-placement.mjs [dir ...]     default: every repository in the registry
 */

import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, resolve, basename } from 'node:path';
import { readRegistry, presentRepos, step, ok, fail, warn, dim } from './lib.mjs';

const branchOf = (dir) => {
  const r = spawnSync('git', ['-C', dir, 'rev-parse', '--abbrev-ref', 'HEAD'], { encoding: 'utf8' });
  return (r.stdout || '').trim();
};

const registry = readRegistry();
const explicit = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const targets = explicit.length
  ? explicit.map((p) => ({ name: basename(resolve(p)), path: resolve(p), directory: basename(resolve(p)) }))
  : presentRepos();

step('Task specifications are on task branches');

let bad = 0;
let checked = 0;

for (const repo of targets) {
  if (repo.name === 'marp-video-server') continue;

  const branch = branchOf(repo.path);
  if (!branch) { warn(`${repo.name} — not a git checkout`); continue; }

  const entry = registry.find((e) => e.directory === repo.directory || e.name === repo.name);
  /* An integration branch is the one the registry says work is based on, plus master,
     which is production everywhere in this platform. */
  const integration = new Set([entry?.default_branch, 'master', 'main'].filter(Boolean));
  if (!integration.has(branch)) { checked++; continue; }

  checked++;
  if (!existsSync(join(repo.path, '.marp', 'task.md'))) { ok(`${repo.name} (${branch}) — clean`); continue; }

  fail(`${repo.name} (${branch}) — carries .marp/task.md`);
  console.log(`         ${dim('a merged spec reads as current. Retire it: marp spec retire ' + repo.directory)}`);
  bad++;
}

if (!checked) warn('nothing to check');
process.exit(bad ? 1 : 0);
