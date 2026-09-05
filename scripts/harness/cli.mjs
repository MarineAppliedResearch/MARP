/**
 * `marp harness|spec|verify|worktree` — the harness half of the workspace tool.
 *
 * Delegated to from `marp.sh` and `marp.ps1` the same way `db` is: these commands are
 * about tasks and instruction files rather than about repositories, and keeping them
 * separate means neither file has to be read to understand the other.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, rmSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { HARNESS_DIR, UMBRELLA, readRegistry, walk, step, ok, warn, fail, dim, cyan } from './lib.mjs';

const [group, sub, ...rest] = process.argv.slice(2);

const run = (script, args = []) =>
  spawnSync(process.execPath, [join(HARNESS_DIR, script), ...args], { stdio: 'inherit' }).status ?? 1;

const git = (args, cwd = UMBRELLA) =>
  spawnSync('git', args, { cwd, encoding: 'utf8' });

function usage(code = 0) {
  console.log(`Usage: marp <harness|spec|verify|worktree> <command> [arguments]

  harness check              every check: shared blocks, instruction files
  harness sync               rewrite each component's shared block from AGENTS.md
  harness install            (re)install the per-repository adapter files

  spec check [dir]           gate G1: is the design settled? Exit 1 if not.
  spec new <task> [dir]      start .marp/task.md from the template
  spec retire [dir]          remove the spec once its branch has merged, so it
                             cannot be read as current on an integration branch

  verify plan [dir]          gate G3: draft .marp/verification.md, including the
                             requirements that have no test against them
  verify run [dir]           gate G4: run the WHOLE suite once the work is done and
                             append the real results, failures included

  agent start <repo> <branch>  an isolated copy on its own branch, with its own
                               database, its own ports, a written .env and
                               dependencies installed -- ready to run and test
  agent list                   what is set up, and on which ports
  agent env <branch>           print those settings again
  agent stop <branch>          stop that agent's database, keep the work
  agent remove <branch>        throw the working copy away, keep the branch`);
  process.exit(code);
}

/* ------------------------------------------------------------------ harness */

if (group === 'harness') {
  if (sub === 'check') process.exit(run('check.mjs'));
  if (sub === 'sync') process.exit(run('sync.mjs', rest));
  if (sub === 'install') process.exit(run('install.mjs'));
  usage(2);
}

/* --------------------------------------------------------------------- spec */

if (group === 'spec') {
  if (sub === 'check') process.exit(run('spec-check.mjs', rest));

  if (sub === 'new') {
    const [task, dir = process.cwd()] = rest;
    if (!task) { fail('name the task, e.g. marp spec new MARP_API#68'); process.exit(2); }
    const target = join(resolve(dir), '.marp', 'task.md');
    if (existsSync(target)) { fail(`${target} already exists`); process.exit(1); }
    mkdirSync(join(resolve(dir), '.marp'), { recursive: true });
    const template = readFileSync(join(UMBRELLA, '.marp', 'task.template.md'), 'utf8');
    writeFileSync(target, template.replace('MarineAppliedResearch/<repo>#<n>', task)
      .replace('[<repo>]', `[${basename(resolve(dir))}]`), 'utf8');
    ok(`${target} — fill in the goal, the requirements, and every assumption you are making`);
    process.exit(0);
  }
  if (sub === 'retire') {
    const dir = resolve(rest[0] || process.cwd());
    const gone = [];
    for (const name of ['task.md', 'verification.md']) {
      const path = join(dir, '.marp', name);
      if (!existsSync(path)) continue;
      /* `git rm` when it is tracked, so the removal is staged and shows in the diff
         rather than looking like a stray deleted file. */
      const tracked = spawnSync('git', ['-C', dir, 'ls-files', '--error-unmatch', `.marp/${name}`],
        { stdio: 'ignore' }).status === 0;
      if (tracked) spawnSync('git', ['-C', dir, 'rm', '-q', `.marp/${name}`], { stdio: 'inherit' });
      else rmSync(path);
      gone.push(name);
    }
    if (!gone.length) { ok('nothing to retire'); process.exit(0); }
    ok(`retired ${gone.join(' and ')}`);
    console.log(dim('    The record lives in the merge commit, the issue, and any decision record.'));
    process.exit(0);
  }

  usage(2);
}

/* ------------------------------------------------------------------- verify */

/** Requirement ids a repository's tests actually reference. */
function requirementsCovered(dir) {
  const covered = new Set();
  for (const file of walk(dir)) {
    if (!/[\\/](tests?|spec|__tests__)[\\/]/i.test(file)) continue;
    if (!/\.(m?[jt]s|py|cs)$/i.test(file)) continue;
    let text;
    try { text = readFileSync(file, 'utf8'); } catch { continue; }
    for (const m of text.matchAll(/\bR\d+\b/g)) covered.add(m[0]);
  }
  return covered;
}

if (group === 'verify') {
  const dir = resolve(rest[0] || process.cwd());
  const specPath = join(dir, '.marp', 'task.md');

  if (!existsSync(specPath)) {
    fail('no .marp/task.md — there is nothing to verify against. Start with: marp spec new');
    process.exit(2);
  }

  if (sub === 'plan') {
    const spec = readFileSync(specPath, 'utf8');
    const reqs = [...spec.matchAll(/^\s*(?:-\s*)?\*\*\s*(R\d+)\s*\*\*\s*(?:[—-]\s*)?(.*)$/gm)]
      .map((m) => ({ id: m[1], text: m[2].trim() }));

    if (!reqs.length) warn('the spec has no numbered requirements, so nothing can be traced to a test');

    const covered = requirementsCovered(dir);
    const gaps = reqs.filter((r) => !covered.has(r.id));

    const template = readFileSync(join(UMBRELLA, '.marp', 'verification.template.md'), 'utf8');
    const table = reqs.length
      ? reqs.map((r) => `| ${r.id} | ${covered.has(r.id) ? '(named in the suite)' : '**none**'} | ? | ${r.text} |`).join('\n')
      : '| | | | |';

    const gapList = gaps.length
      ? gaps.map((r) => `- **${r.id}** — ${r.text}`).join('\n')
      : '_None. Every numbered requirement is referenced by at least one test._';

    const out = template
      .replace('# Verification — <task>', `# Verification — ${(spec.match(/^task:\s*(.*)$/m) || [, dir])[1]}`)
      .replace(/\| R1 \| … \| unit \| … \|\n\| R2 \| … \| render \| … \|/, table)
      .replace(/List them\. This section being empty is a claim[\s\S]*?the tests reference\./,
        gapList + '\n\n<!-- Drafted by `marp verify plan` from the requirement ids the suite mentions.\n     A requirement is "covered" here only in the sense that some test names it. Whether\n     that test proves it is the thing a human is reviewing. -->');

    writeFileSync(join(dir, '.marp', 'verification.md'), out, 'utf8');
    step('Verification plan');
    ok(`${reqs.length} requirements, ${covered.size} referenced by tests`);
    if (gaps.length) fail(`${gaps.length} requirement(s) with no test: ${gaps.map((r) => r.id).join(', ')}`);
    console.log(dim('    Written to .marp/verification.md. A human reviews this BEFORE anything runs.'));
    process.exit(0);
  }

  if (sub === 'run') {
    const pkg = join(dir, 'package.json');
    if (!existsSync(pkg)) { fail('no package.json — run this repository\'s own tiers by hand and record the output'); process.exit(2); }
    const scripts = JSON.parse(readFileSync(pkg, 'utf8')).scripts || {};

    /*
     * The whole suite, not the fast tiers.
     *
     * This is gate G4: the run that has to pass before anything is called done. Run it
     * as often as the work needs -- it is a gate, not a budget. An earlier version ran
     * only lint and unit tests to stay quick, which got it backwards: the quick loop is
     * `npm run test:unit` after every change, and this is the thorough one, which has to
     * be able to see a broken dialog.
     */
    const tiers = scripts.test
      ? ['test']
      : ['lint', 'test:unit', 'test:e2e'].filter((t) => scripts[t]);
    if (!tiers.length) { fail('no test script here'); process.exit(2); }
    console.log(dim('    The full suite, including the slow tiers. This is the run a human reviews.'));

    const lines = [];
    let failed = 0;
    for (const tier of tiers) {
      step(`npm run ${tier}`);
      const r = spawnSync('npm', ['run', tier], { cwd: dir, encoding: 'utf8', shell: true });
      const output = (r.stdout || '') + (r.stderr || '');
      process.stdout.write(output);
      if (r.status !== 0) failed++;
      lines.push(`### \`npm run ${tier}\` — ${r.status === 0 ? 'passed' : 'FAILED'}\n\n\`\`\`\n${output.trim().slice(-4000)}\n\`\`\`\n`);
    }

    const vpath = join(dir, '.marp', 'verification.md');
    const existing = existsSync(vpath) ? readFileSync(vpath, 'utf8') : '## Results\n';
    writeFileSync(vpath, existing.replace(/<!-- Appended by[\s\S]*?-->/, '').trimEnd() +
      `\n\n### Run ${new Date().toISOString().slice(0, 16).replace('T', ' ')}\n\n` + lines.join('\n'), 'utf8');

    if (failed) { fail(`${failed} tier(s) failed — the output above is what goes to the human, verbatim`); process.exit(1); }
    ok('the whole suite passed; manual steps and walkthroughs are still yours to run');
    process.exit(0);
  }
  usage(2);
}

/* -------------------------------------------------------------------- agent */

if (group === 'agent' || group === 'worktree') {
  // `worktree` kept as an alias for one release: the concept is "an agent works on its
  // own branch, in its own copy, on its own ports", and naming it after the git feature
  // underneath was confusing rather than descriptive.
  process.exit(spawnSync(process.execPath, [join(HARNESS_DIR, 'agent.mjs'), ...process.argv.slice(3)],
    { stdio: 'inherit' }).status ?? 1);
}

usage(group ? 2 : 0);
