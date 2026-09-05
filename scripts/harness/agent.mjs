/**
 * `marp agent` — set up an isolated working copy so an agent can run and test on its own.
 *
 * The model is deliberately simple: **an agent works on its own branch, in its own copy of
 * the repository, against its own database, on its own ports.** It runs its own tests,
 * reports back, and pushes the branch. Branches get merged the usual way. Nothing is
 * shared between two agents except the things that are meant to be shared.
 *
 * On one machine the isolated copy is a git worktree, which shares the object store and so
 * costs almost nothing. On a second machine it is just a normal clone on a branch — the
 * same model, and `marp agent env` prints the settings that keep it from colliding with
 * anything else.
 *
 * What is NOT isolated, on purpose:
 *
 *   - **Jellyfin.** Every agent talks to the central MARP media server. It holds the real
 *     library, the tests that touch it read far more than they write, and standing one up
 *     per agent would be absurd. A task that genuinely needs its own Jellyfin says so and
 *     gets one; nothing else should.
 *   - **The PostgreSQL binaries.** Downloaded once into .postgres/ and shared. Only the
 *     data directory is per-agent.
 *
 * Usage:
 *   marp agent start <repo> <branch>   isolated copy, database, ports, .env, dependencies
 *   marp agent list                    what is set up, and on which ports
 *   marp agent env <branch>            print the settings again
 *   marp agent stop <branch>           stop that agent's database, keep the work
 *   marp agent remove <branch>         throw the whole thing away
 */

import { spawnSync, execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync, cpSync, statSync } from 'node:fs';
import { createServer } from 'node:net';
import { createHash } from 'node:crypto';
import { join, resolve, relative, sep } from 'node:path';
import { UMBRELLA, readRegistry, step, ok, warn, fail, dim, cyan } from './lib.mjs';

/** Where isolated copies live. Outside the umbrella, so it never sees them. */
const ROOT = resolve(UMBRELLA, '..', 'marp-agents');

/** Ports are searched from here upwards, so an agent never lands on a default. */
const API_BASE = 3010;
const DB_BASE = 5450;

const isFree = (port) => new Promise((done) => {
  const s = createServer();
  s.once('error', () => done(false));
  s.once('listening', () => s.close(() => done(true)));
  s.listen(port, '127.0.0.1');
});

async function freePort(from, taken) {
  for (let p = from; p < from + 200; p++) {
    if (taken.has(p)) continue;
    if (await isFree(p)) return p;
  }
  throw new Error(`no free port from ${from}`);
}

/** Every agent's recorded settings, so ports are never handed out twice. */
function readAgents() {
  if (!existsSync(ROOT)) return [];
  const out = [];
  for (const entry of readdirSync(ROOT, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const meta = join(ROOT, entry.name, '.marp-agent.json');
    if (!existsSync(meta)) continue;
    try { out.push({ ...JSON.parse(readFileSync(meta, 'utf8')), dir: join(ROOT, entry.name) }); }
    catch { /* unreadable; treat as absent */ }
  }
  return out;
}

const git = (args, cwd) => spawnSync('git', args, { cwd, encoding: 'utf8' });

/** How many files ended up somewhere — reported so a silent empty copy is visible. */
function countFiles(dir) {
  let n = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) n += countFiles(full);
    else if (statSync(full).isFile()) n++;
  }
  return n;
}

/**
 * Every directory here that is its own npm package with its own lock file.
 *
 * Shallow on purpose: applications live a few levels down, and walking the whole tree
 * would find fixtures and vendored copies that nobody wants installed.
 */
function packageDirs(root, depth = 0) {
  const found = [];
  if (existsSync(join(root, 'package.json')) && existsSync(join(root, 'package-lock.json'))) {
    found.push(root);
  }
  if (depth >= 4) return found;
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    found.push(...packageDirs(join(root, entry.name), depth + 1));
  }
  return found;
}

/** A branch name has to survive being a directory name and a database directory. */
const slug = (s) => s.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);

/**
 * Carry the settings that are shared rather than per-agent out of the developer's own
 * `.env`: the Jellyfin credentials and anything else this repository needs to talk to a
 * central service. They are never stored in the harness and never committed.
 */
function sharedEnvLines(repoPath) {
  const source = join(repoPath, '.env');
  if (!existsSync(source)) return { lines: [], found: false };
  const keep = /^(JELLYFIN_|REPORT_|HOSTNAME=|VIDEO_ENGINE_)/;
  const lines = readFileSync(source, 'utf8').split(/\r?\n/)
    .filter((l) => keep.test(l.trim()));
  return { lines, found: lines.length > 0 };
}

/**
 * The ports this checkout's Playwright configs will serve on.
 *
 * Mirrors the derivation in `playwright.config.mjs`: a hash of the config file's own
 * absolute path. Duplicated deliberately and narrowly -- the alternative is importing an
 * application's config from the workspace tool, which couples them far worse.
 */
function playwrightPorts(root) {
  const ports = [];
  for (const dir of packageDirs(root)) {
    const cfg = join(dir, 'playwright.config.mjs');
    if (!existsSync(cfg)) continue;
    const hash = createHash('sha1').update(cfg).digest('hex').slice(0, 6);
    ports.push(8100 + (parseInt(hash, 16) % 700));
  }
  return ports;
}

/** What is listening on a port, and who owns it. Windows and POSIX differ; both are tried. */
function listenerPid(port) {
  if (process.platform === 'win32') {
    const r = spawnSync('powershell', ['-NoProfile', '-Command',
      `(Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess`],
      { encoding: 'utf8' });
    const pid = Number((r.stdout || '').trim());
    return Number.isInteger(pid) && pid > 0 ? pid : null;
  }
  const r = spawnSync('lsof', ['-nP', `-iTCP:${port}`, '-sTCP:LISTEN', '-t'], { encoding: 'utf8' });
  const pid = Number(String(r.stdout || '').match(/[0-9]+/) || [0]);
  return Number.isInteger(pid) && pid > 0 ? pid : null;
}

function stopListener(port) {
  const pid = listenerPid(port);
  if (!pid) return false;
  if (process.platform === 'win32') {
    spawnSync('powershell', ['-NoProfile', '-Command', `Stop-Process -Id ${pid} -Force`], { stdio: 'ignore' });
  } else {
    spawnSync('kill', ['-9', String(pid)], { stdio: 'ignore' });
  }
  return true;
}

/* --------------------------------------------------------------------- start */

async function start(repoName, branch) {
  const entry = readRegistry().find((e) => e.name === repoName || e.directory === repoName);
  if (!entry) { fail(`${repoName} is not in services/repos.yml`); process.exit(2); }

  const repoPath = join(UMBRELLA, entry.directory);
  if (!existsSync(join(repoPath, '.git'))) {
    fail(`${entry.directory} is not cloned. Run: marp clone ${entry.name}`);
    process.exit(2);
  }

  const name = `${entry.directory}--${slug(branch)}`;
  const dir = join(ROOT, name);
  if (existsSync(dir)) { fail(`${dir} already exists. Use: marp agent remove ${branch}`); process.exit(1); }

  const base = entry.default_branch || 'develop';
  step(`${entry.name}: ${branch} from origin/${base}`);

  git(['fetch', 'origin', base], repoPath);
  mkdirSync(ROOT, { recursive: true });
  const add = git(['worktree', 'add', '-b', branch, dir, `origin/${base}`], repoPath);
  if (add.status !== 0) { fail((add.stderr || '').trim()); process.exit(1); }
  ok(dir);

  /* Ports first, so the .env below is written once and is correct. */
  const taken = new Set(readAgents().flatMap((a) => [a.apiPort, a.dbPort]));
  const apiPort = await freePort(API_BASE, taken);
  const needsDb = existsSync(join(dir, 'scripts', 'init-database.js'));
  const dbPort = needsDb ? await freePort(DB_BASE, taken) : null;

  /* The app's Playwright config derives its own port from the config file's path, so
     record it here too -- otherwise nothing but that config knows the number, and a
     server left behind on it cannot be found again. */
  const testPorts = playwrightPorts(dir);
  const meta = {
    name, repo: entry.name, directory: entry.directory, branch,
    apiPort, dbPort, testPorts, created: new Date().toISOString(),
  };
  writeFileSync(join(dir, '.marp-agent.json'), JSON.stringify(meta, null, 2) + '\n');
  ok(`api port ${apiPort}${dbPort ? `, database port ${dbPort}` : ''}`);

  if (needsDb) {
    step('Its own database');
    const script = process.platform === 'win32' ? 'db.ps1' : 'db.sh';
    const args = process.platform === 'win32'
      ? ['-NoProfile', '-File', join(UMBRELLA, 'scripts', script), 'up', '-Port', String(dbPort), '-DataDirName', name, '-Quiet']
      : [join(UMBRELLA, 'scripts', script), 'up', '--port', String(dbPort), '--data-dir', name];
    const cmd = process.platform === 'win32' ? 'powershell' : 'sh';
    const r = spawnSync(cmd, args, { stdio: 'inherit' });
    if (r.status !== 0) {
      warn('the database did not come up; the working copy is fine, fix the database and rerun `marp db up` for it');
    } else {
      ok(`database on 127.0.0.1:${dbPort}`);
    }

    step('.env');
    const shared = sharedEnvLines(repoPath);
    const env = [
      '# Written by `marp agent start`. Never commit this file.',
      '#',
      '# This agent has its own database and its own API port so it cannot collide with',
      '# another agent, or with your own development server. Jellyfin is deliberately NOT',
      '# per-agent: everything points at the central MARP media server.',
      '',
      'NODE_ENV=development',
      `PORT=${apiPort}`,
      '',
      'DB_HOST=127.0.0.1',
      `DB_PORT=${dbPort}`,
      'DB_NAME=mare_v1',
      'DB_USER=marp_user',
      'DB_PASSWORD=marp_dev_password',
      'DB_DIALECT=postgres',
      '',
      `AUTH_SESSION_SECRET=agent-${slug(branch)}-${Math.random().toString(36).slice(2, 12)}`,
      '',
    ];
    if (shared.found) {
      env.push('# Carried over from your own .env: the central services, not per-agent.', ...shared.lines, '');
      ok(`${shared.lines.length} shared settings carried over (Jellyfin and friends)`);
    } else {
      warn(`no ${entry.directory}/.env to carry Jellyfin settings from — routes that resolve media will not work`);
    }
    writeFileSync(join(dir, '.env'), env.join('\n'));
    ok('.env written');
  }

  /*
   * Runtime directories that are git-ignored, so a fresh copy gets the empty shell.
   *
   * `storage/` is the one that bites: 646 species pictures live there as files, and the
   * database only holds their names. `db up` builds the schema by driving the *main*
   * checkout, so the migration that imports those files copies them into that checkout's
   * storage, never the agent's. The result was four tests failing in an isolated copy that
   * pass everywhere else — and failing for a reason that looks nothing like the cause.
   *
   * Copied rather than linked: an agent that writes a picture should not be writing into
   * somebody else's working copy, which is the whole point of the isolation.
   */
  for (const runtime of ['storage']) {
    const from = join(repoPath, runtime);
    if (!existsSync(from)) continue;
    step(`${runtime}/`);
    try {
      cpSync(from, join(dir, runtime), { recursive: true, force: true });
      const files = countFiles(join(dir, runtime));
      ok(`${files} file${files === 1 ? '' : 's'} copied — git-ignored, so a clone does not bring them`);
    } catch (error) {
      warn(`could not copy ${runtime}/: ${error.message}`);
    }
  }

  /*
   * Dependencies, including the nested packages.
   *
   * `npm ci` at the root installs the root only. marp-api's frontend applications are
   * separate packages with their own lock files -- deliberately, so one can be extracted
   * later -- and an agent that starts work on an application finds no node_modules and no
   * test runner. That was the first thing to go wrong the first time this was used.
   */
  for (const pkgDir of packageDirs(dir)) {
    const where = pkgDir === dir ? 'root' : relative(dir, pkgDir).split(sep).join('/');
    step(`Dependencies (${where})`);
    const r = spawnSync('npm', ['ci'], { cwd: pkgDir, stdio: 'inherit', shell: true });
    if (r.status !== 0) warn(`npm ci failed in ${where} — run it yourself`);
    else ok('installed');
  }

  mkdirSync(join(dir, '.marp'), { recursive: true });
  const template = join(UMBRELLA, '.marp', 'task.template.md');
  if (existsSync(template) && !existsSync(join(dir, '.marp', 'task.md'))) {
    writeFileSync(join(dir, '.marp', 'task.md'), readFileSync(template, 'utf8'));
    ok('.marp/task.md seeded — fill it in; the G1 gate blocks edits until its assumptions are answered');
  }

  console.log('');
  console.log(cyan('  Ready. From that directory:'));
  console.log(`    npm run dev            ${dim(`# http://localhost:${apiPort}`)}`);
  console.log(`    npm test               ${dim(dbPort ? `# against its own database on ${dbPort}` : '# no database needed here')}`);
  console.log('');
  console.log(dim(`  On another machine, clone the repository and check out ${branch} instead;`));
  console.log(dim('  the model is the same and `marp agent env` prints these settings.'));
}

/* ---------------------------------------------------------------- list / env */

function list() {
  const agents = readAgents();
  step('Agents');
  if (!agents.length) { ok('none set up'); return; }
  for (const a of agents) {
    console.log(`  ${cyan(a.branch)}  ${a.repo}`);
    console.log(`    ${a.dir}`);
    console.log(`    api ${a.apiPort}${a.dbPort ? `, database ${a.dbPort}` : ''}   ${dim(a.created.slice(0, 16).replace('T', ' '))}`);
  }
}

function find(branch) {
  const a = readAgents().find((x) => x.branch === branch || x.name === branch);
  if (!a) { fail(`no agent for "${branch}". See: marp agent list`); process.exit(2); }
  return a;
}

function env(branch) {
  const a = find(branch);
  const path = join(a.dir, '.env');
  if (existsSync(path)) { process.stdout.write(readFileSync(path, 'utf8')); return; }
  console.log(`PORT=${a.apiPort}`);
  if (a.dbPort) console.log(`DB_HOST=127.0.0.1\nDB_PORT=${a.dbPort}\nDB_NAME=mare_v1`);
}

/* -------------------------------------------------------------- stop / remove */

function db(a, command) {
  if (!a.dbPort) return;
  const win = process.platform === 'win32';
  const script = join(UMBRELLA, 'scripts', win ? 'db.ps1' : 'db.sh');
  const args = win
    ? ['-NoProfile', '-File', script, command, '-Port', String(a.dbPort), '-DataDirName', a.name]
    : [script, command, '--port', String(a.dbPort), '--data-dir', a.name];
  spawnSync(win ? 'powershell' : 'sh', args, { stdio: 'inherit' });
}

/**
 * Stop everything this agent left running.
 *
 * A server outliving the work that started it is not untidiness. One left running in a
 * different checkout was adopted by another workspace's browser tests, which then graded
 * that checkout's code for an hour without saying so.
 */
function stopServers(a) {
  const ports = [a.apiPort, ...(a.testPorts || [])].filter(Boolean);
  const stopped = ports.filter((p) => stopListener(p));
  if (stopped.length) ok(`stopped servers on ${stopped.join(', ')}`);
  return stopped.length;
}

function stop(branch) {
  const a = find(branch);
  step(`Stopping ${a.branch}`);
  stopServers(a);
  db(a, 'down');
  ok('database stopped; the working copy and the branch are untouched');
}

function remove(branch) {
  const a = find(branch);
  step(`Removing ${a.branch}`);
  stopServers(a);
  db(a, 'destroy');

  const repoPath = join(UMBRELLA, a.directory);
  const r = git(['worktree', 'remove', '--force', a.dir], repoPath);
  if (r.status !== 0) {
    warn((r.stderr || '').trim());
    try { rmSync(a.dir, { recursive: true, force: true }); } catch { /* held open */ }
  }
  git(['worktree', 'prune'], repoPath);

  // The branch is deliberately kept. Removing a working copy is tidying up; deleting a
  // branch is throwing work away, and the two should never be the same command.
  ok(`working copy gone. The branch ${a.branch} is kept — delete it yourself if it is finished.`);
}

/* ------------------------------------------------------------------ dispatch */

const [sub, ...rest] = process.argv.slice(2);

if (sub === 'start') {
  const [repo, branch] = rest;
  if (!repo || !branch) { fail('usage: marp agent start <repo> <branch>'); process.exit(2); }
  await start(repo, branch);
} else if (sub === 'list' || !sub) {
  list();
} else if (sub === 'env') {
  if (!rest[0]) { fail('usage: marp agent env <branch>'); process.exit(2); }
  env(rest[0]);
} else if (sub === 'stop') {
  if (!rest[0]) { fail('usage: marp agent stop <branch>'); process.exit(2); }
  stop(rest[0]);
} else if (sub === 'remove') {
  if (!rest[0]) { fail('usage: marp agent remove <branch>'); process.exit(2); }
  remove(rest[0]);
} else {
  fail(`unknown: marp agent ${sub}`);
  console.log(dim('  start | list | env | stop | remove'));
  process.exit(2);
}
