/**
 * Two agents that do not know about each other.
 *
 * Parallelism after the design is settled is the whole point; two agents quietly editing
 * the same surface, or both claiming a resource that only exists once, is the failure it
 * has to avoid. Nothing read the specs' `repos:` or `needs:` fields until now, so both
 * were declarations with no teeth.
 *
 * Reports rather than blocks. Two agents on one repository is often exactly right --
 * different files, different tasks -- so this says what overlaps and lets a human decide.
 * A shared `needs:` is different: those are exclusive by definition, and it fails.
 *
 *   node agent-conflicts.mjs
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { UMBRELLA, step, ok, fail, warn, dim, cyan } from './lib.mjs';

const ROOT = resolve(UMBRELLA, '..', 'marp-agents');

/** Front matter fields a spec uses to say what it touches. */
function readSpec(dir) {
  const path = join(dir, '.marp', 'task.md');
  if (!existsSync(path)) return { repos: [], needs: [] };
  const text = readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
  const front = text.startsWith('---') ? text.slice(3, text.indexOf('\n---', 3)) : '';
  /* Parsed by hand rather than by regular expression: the front matter is one flat line
     per key, and a pattern built from a template literal lost its escapes silently and
     returned nothing for every key -- which looked exactly like "no conflicts". */
  const list = (key) => {
    const line = front.split('\n').find((l) => l.trim().startsWith(`${key}:`));
    if (!line) return [];
    const open = line.indexOf('[');
    const close = line.lastIndexOf(']');
    if (open < 0 || close < open) return [];
    return line.slice(open + 1, close).split(',').map((v) => v.trim()).filter(Boolean);
  };
  return { repos: list('repos'), needs: list('needs') };
}

const agents = [];
if (existsSync(ROOT)) {
  for (const entry of readdirSync(ROOT, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const dir = join(ROOT, entry.name);
    const metaPath = join(dir, '.marp-agent.json');
    if (!existsSync(metaPath)) continue;
    try {
      const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
      agents.push({ ...meta, dir, ...readSpec(dir) });
    } catch { /* unreadable; treat as absent */ }
  }
}

step('Agents working in parallel');

if (agents.length < 2) {
  ok(agents.length ? '1 agent set up; nothing to collide with' : 'none set up');
  process.exit(0);
}

let failures = 0;

/* Ports first: two agents on one port is not a judgement call, it is broken. */
const byPort = new Map();
for (const a of agents) {
  for (const [kind, port] of [['api', a.apiPort], ['database', a.dbPort], ...(a.testPorts || []).map((p) => ['test', p])]) {
    if (!port) continue;
    const key = `${kind}:${port}`;
    if (byPort.has(key)) {
      fail(`${a.branch} and ${byPort.get(key)} both claim ${kind} port ${port}`);
      failures++;
    } else byPort.set(key, a.branch);
  }
}

/* An exclusive resource claimed twice. `needs:` exists precisely to say "only one of
   these at a time" -- the Jellyfin development instance is one machine. */
const byNeed = new Map();
for (const a of agents) {
  for (const need of a.needs) {
    if (byNeed.has(need)) {
      fail(`${a.branch} and ${byNeed.get(need)} both need "${need}", which only exists once`);
      failures++;
    } else byNeed.set(need, a.branch);
  }
}

/* Same repository is a warning, not a failure: usually it is two unrelated tasks. */
const byRepo = new Map();
for (const a of agents) {
  const declared = a.repos.length ? a.repos : [a.directory];
  for (const repo of declared) {
    (byRepo.get(repo) || byRepo.set(repo, []).get(repo)).push(a.branch);
  }
}
for (const [repo, branches] of byRepo) {
  if (branches.length < 2) continue;
  warn(`${branches.length} agents on ${repo}: ${branches.join(', ')}`);
  console.log(`         ${dim('fine if they are different work; check the specs agree on the interfaces')}`);
}

if (!failures) ok(`${agents.length} agents, no conflicting ports or exclusive resources`);
else console.log(dim('\n    Fix with: marp agent remove <branch>, then start it again.'));

process.exit(failures ? 1 : 0);
