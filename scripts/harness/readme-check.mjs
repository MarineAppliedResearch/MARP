/**
 * The README rules that a synced block cannot carry.
 *
 * `sync.mjs` keeps the identity block identical everywhere, which settles the statement
 * and the cross-links. Three things sit outside it and still have to agree:
 *
 * - **The logo.** Every repository carries its own copy, because a README on GitHub
 *   cannot reach across repositories with a relative path. So the block cannot hold the
 *   path, and what is checked instead is that a copy exists and that the README shows it.
 * - **The badge row.** The colours are the platform's, and they were quietly wrong before
 *   anything looked: `0b7285` is a teal from a retired palette, and `a7e735` is
 *   `--green-400` with two digits transposed. A convention nobody checks is a convention
 *   that drifts back.
 * - **The retired name.** `MARE_API` still redirects on GitHub, so a stale link works
 *   right up until somebody creates a repository with that name. marp-video-player
 *   carried two of them for months and nothing said so.
 *
 * Usage:
 *   node readme-check.mjs
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { UMBRELLA, BRANDED, step, ok, fail, warn, dim } from './lib.mjs';

/** The platform colours, from `frontend/shared/assets/css/tokens.css`. */
const CYAN = '05b9c8';
const GREEN = 'a7ec35';

/** The status badge every MARP repository carries, identical down to the colour. */
const STATUS_BADGE = `status-internal%20production%20%7C%20active%20development-${CYAN}`;

/** The umbrella is checked alongside the components; it is the one they copy from. */
const TARGETS = [{ name: 'MARP', path: UMBRELLA }, ...BRANDED()];

let bad = 0;

step('Checking README branding');

for (const repo of TARGETS) {
  const path = join(repo.path, 'README.md');
  const label = `${repo.name}/README.md`;

  if (!existsSync(path)) {
    fail(`${label} — missing`);
    bad++;
    continue;
  }

  const text = readFileSync(path, 'utf8');
  const problems = [];

  // The logo has to be shown, and the file it points at has to be there. Checking only
  // for the markup is how the developer documentation 404'd its own logo for months.
  const shown = [...text.matchAll(/<img[^>]+src="([^"]*marp-logo\.png)"/g)].map((m) => m[1]);

  if (!shown.length) {
    problems.push('does not show marp-logo.png');
  } else {
    const broken = shown.filter((src) => !existsSync(join(repo.path, src)));
    if (broken.length) problems.push(`points at a logo that is not in the repository: ${broken.join(', ')}`);
  }

  if (!text.includes(STATUS_BADGE)) {
    problems.push(`no status badge on ${CYAN}`);
  }

  // Only where there is a licence to name. The umbrella has no LICENSE file.
  if (existsSync(join(repo.path, 'LICENSE')) && !/img\.shields\.io\/badge\/license-[^"'\s]*-a7ec35/.test(text)) {
    problems.push(`no licence badge on ${GREEN}`);
  }

  // A link, not the word. The umbrella explains the rename in prose and should.
  const retired = [...text.matchAll(/github\.com\/MarineAppliedResearch\/MARE_API/g)];
  if (retired.length) {
    problems.push(`${retired.length} link(s) to the retired MARE_API name`);
  }

  if (!problems.length) {
    ok(`${label} — branded`);
    continue;
  }

  fail(label);
  for (const problem of problems) console.log(`         ${dim(problem)}`);
  bad++;
}

if (bad) {
  console.log('');
  fail(`${bad} README(s) off the platform branding`);
  process.exit(1);
}

warn('marp-video-server and video-processing-gui are excluded on purpose; see BRANDED in lib.mjs');
process.exit(0);
