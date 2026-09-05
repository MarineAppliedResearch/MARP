/**
 * `marp harness|spec|verify|worktree` — the harness half of the workspace tool.
 *
 * Delegated to from `marp.sh` and `marp.ps1` the same way `db` is: these commands are
 * about tasks and instruction files rather than about repositories, and keeping them
 * separate means neither file has to be read to understand the other.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
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

  verify plan [dir]          gate G3: draft .marp/verification.md, including the
                             requirements that have no test against them
  verify run [dir]           run the fast tiers and append real results

  worktree <repo> <issue>    a new branch in its own worktree, spec seeded
  worktree list              what is checked out where`);
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

    // Only the fast tiers. Browser, database and hardware suites belong to the person
    // working, and to gate G4 -- running them here would make this command slow enough
    // that nobody runs it.
    const tiers = ['lint', 'test:unit'].filter((t) => scripts[t]);
    if (!tiers.length) { fail('no lint or test:unit script here'); process.exit(2); }

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
    ok('fast tiers passed; slow tiers and manual steps are still yours to run');
    process.exit(0);
  }
  usage(2);
}

/* ----------------------------------------------------------------- worktree */

if (group === 'worktree') {
  const root = resolve(UMBRELLA, '..', 'marp-worktrees');

  if (sub === 'list' || !sub) {
    step('Worktrees');
    for (const entry of readRegistry()) {
      const repoPath = join(UMBRELLA, entry.directory);
      if (!existsSync(join(repoPath, '.git'))) continue;
      const r = git(['worktree', 'list'], repoPath);
      const extra = (r.stdout || '').trim().split('\n').slice(1);
      if (extra.length && extra[0]) {
        console.log(cyan(`  ${entry.name}`));
        extra.forEach((l) => console.log(`    ${l}`));
      }
    }
    process.exit(0);
  }

  const [repoName, issue] = [sub, rest[0]];
  if (!issue) { fail('usage: marp worktree <repo> <issue-branch-name>'); process.exit(2); }

  const entry = readRegistry().find((e) => e.name === repoName || e.directory === repoName);
  if (!entry) { fail(`${repoName} is not in services/repos.yml`); process.exit(2); }

  const repoPath = join(UMBRELLA, entry.directory);
  const base = entry.default_branch || 'develop';
  const dest = join(root, entry.directory, issue);

  step(`${entry.name}: ${issue} from origin/${base}`);
  git(['fetch', 'origin', base], repoPath);
  const add = git(['worktree', 'add', '-b', issue, dest, `origin/${base}`], repoPath);
  if (add.status !== 0) { fail((add.stderr || '').trim()); process.exit(1); }
  ok(dest);

  mkdirSync(join(dest, '.marp'), { recursive: true });
  copyFileSync(join(UMBRELLA, '.marp', 'task.template.md'), join(dest, '.marp', 'task.md'));
  ok('.marp/task.md seeded — fill it in before implementing anything');

  // Each worktree needs its own database, or two agents write to one. `db up` takes a
  // port; the data directory is still fixed at the umbrella root, which is the piece
  // that has to change before two of these can run at once on one machine.
  warn('a second worktree on this machine needs its own database: marp db up --port 5440');
  process.exit(0);
}

usage(group ? 2 : 0);
