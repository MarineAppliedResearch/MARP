/**
 * Prove the gates gate.
 *
 * A hook that fails open on every path looks exactly like a hook with nothing to block:
 * green, silent, and useless. Both of these fail open deliberately in several situations,
 * which makes that failure mode easy to reach by accident — so the cases where they must
 * say no are asserted here rather than assumed.
 *
 * No dependencies and no framework: this has to run anywhere the harness does.
 */

import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { HARNESS_DIR, step, ok, fail, dim } from './lib.mjs';

let failures = 0;

function decide(hook, payload) {
  const r = spawnSync(process.execPath, [join(HARNESS_DIR, 'hooks', hook)], {
    input: JSON.stringify(payload), encoding: 'utf8',
  });
  try { return JSON.parse(r.stdout).hookSpecificOutput.permissionDecision; }
  catch { return `unparseable: ${(r.stdout || r.stderr || '').slice(0, 120)}`; }
}

function check(name, actual, expected) {
  if (actual === expected) { ok(`${name} → ${actual}`); return; }
  fail(`${name} → ${actual}, expected ${expected}`);
  failures++;
}

/* A task branch whose design is not settled. */
const root = mkdtempSync(join(tmpdir(), 'marp-harness-'));
const blocked = join(root, 'blocked');
const settled = join(root, 'settled');
const nospec = join(root, 'nospec');

for (const dir of [blocked, settled, nospec]) mkdirSync(join(dir, '.marp'), { recursive: true });

writeFileSync(join(blocked, '.marp', 'task.md'),
  '## Open assumptions\n\n- [ ] **A1 · schema · blocking** — unanswered\n');
writeFileSync(join(settled, '.marp', 'task.md'),
  '## Open assumptions\n\n- [x] **A1 · schema · blocking** — answered\n' +
  '- [ ] **A2 · ui · non-blocking** — still open, deliberately\n');

try {
  step('spec-gate');
  check('blocked spec, editing source', decide('spec-gate.mjs', { cwd: blocked, tool_input: { file_path: 'src/app.js' } }), 'deny');
  check('blocked spec, editing the spec', decide('spec-gate.mjs', { cwd: blocked, tool_input: { file_path: '.marp/task.md' } }), 'allow');
  check('settled spec, editing source', decide('spec-gate.mjs', { cwd: settled, tool_input: { file_path: 'src/app.js' } }), 'allow');
  check('no spec at all', decide('spec-gate.mjs', { cwd: nospec, tool_input: { file_path: 'src/app.js' } }), 'allow');
  check('malformed payload fails open', decide('spec-gate.mjs', {}), 'allow');

  step('danger-gate');
  const cmd = (command) => decide('danger-gate.mjs', { tool_input: { command } });
  check('force push', cmd('git push --force origin develop'), 'deny');
  check('production database', cmd('psql -h db -d mare_v1 -c "select 1"'), 'deny');
  check('live Jellyfin port', cmd('curl http://10.0.0.4:8096/System/Info'), 'deny');
  check('development Jellyfin port', cmd('curl http://10.0.0.4:8097/System/Info'), 'allow');
  check('restoring a retired migration', cmd('cp db/retired-migrations/x.js migrations/'), 'deny');
  check('force branch delete', cmd('git branch -D feature-old'), 'deny');
  check('ordinary push', cmd('git push origin my-branch'), 'ask');
  check('opening a pull request', cmd('gh pr create --fill'), 'ask');
  check('running migrations', cmd('npx sequelize-cli db:migrate'), 'ask');
  check('adding a dependency', cmd('npm install left-pad'), 'ask');
  check('installing what is already declared', cmd('npm ci'), 'allow');
  check('running the tests', cmd('npm test'), 'allow');
  check('listing files', cmd('ls -la'), 'allow');
} finally {
  rmSync(root, { recursive: true, force: true });
}

console.log('');
if (failures) {
  fail(`${failures} gate assertion(s) failed`);
  console.log(dim('    A gate that does not block is indistinguishable from no gate.'));
  process.exit(1);
}
ok('both gates behave as documented');
