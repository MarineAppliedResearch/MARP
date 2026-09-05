/**
 * Everything the harness can check about the workspace, in one command.
 *
 * Runs each check to completion rather than stopping at the first failure: a developer
 * fixing one problem should see all of them, not discover the next one on the next run.
 */

import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { HARNESS_DIR, step, ok, fail, red, green } from './lib.mjs';

const CHECKS = [
  { name: 'shared instruction blocks', script: 'sync.mjs', args: ['--check'] },
  { name: 'instruction files', script: 'doc-check.mjs', args: [] },
  { name: 'the gates', script: 'self-test.mjs', args: [] },
];

const failed = [];

for (const check of CHECKS) {
  const result = spawnSync(process.execPath, [join(HARNESS_DIR, check.script), ...check.args], {
    stdio: 'inherit',
  });
  if (result.status !== 0) failed.push(check.name);
  console.log('');
}

step('Harness check');
if (!failed.length) {
  ok(green('everything the harness can verify is consistent'));
  process.exit(0);
}
for (const name of failed) fail(red(name));
process.exit(1);
