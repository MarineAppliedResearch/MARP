/**
 * Shared helpers for the harness checks.
 *
 * Deliberately dependency-free and Node-only. These run from the umbrella, from a
 * component's CI, and from a Claude Code hook, so anything they need has to be in the
 * standard library.
 */

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const HARNESS_DIR = dirname(fileURLToPath(import.meta.url));
export const UMBRELLA = resolve(HARNESS_DIR, '..', '..');

export const SHARED_START = '<!-- marp:shared start -->';
export const SHARED_END = '<!-- marp:shared end -->';

/* The README's identity block: the one-line statement of what MARP is, and the row of
   links from each repository to all the others. Same mechanism as the shared instruction
   block and for the same reason -- five READMEs describing the platform five ways is what
   this replaced. */
export const BRAND_START = '<!-- marp:brand start -->';
export const BRAND_END = '<!-- marp:brand end -->';

/** ANSI only when something is actually watching; CI logs are worse with escape codes. */
const tty = process.stdout.isTTY && !process.env.CI;
const paint = (code) => (s) => (tty ? `[${code}m${s}[0m` : s);
export const dim = paint('2');
export const red = paint('31');
export const green = paint('32');
export const yellow = paint('33');
export const cyan = paint('36');

export const step = (m) => console.log(cyan(`==> ${m}`));
export const ok = (m) => console.log(`    ${green('ok')}   ${m}`);
export const warn = (m) => console.log(`    ${yellow('note')} ${m}`);
export const fail = (m) => console.log(`    ${red('FAIL')} ${m}`);

/**
 * Read `services/repos.yml` without a YAML library.
 *
 * `marp.ps1` and `marp.sh` already parse it by hand and the file's own header documents
 * the constrained shape that makes this safe: group keys at column 0, repository keys at
 * two spaces, fields at four.
 */
export function readRegistry(umbrella = UMBRELLA) {
  const text = readFileSync(join(umbrella, 'services', 'repos.yml'), 'utf8');
  const entries = [];
  let group = null;
  let current = null;

  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim() || raw.trimStart().startsWith('#')) continue;

    const groupMatch = /^([a-z_]+):\s*$/.exec(raw);
    if (groupMatch) { group = groupMatch[1]; continue; }

    const nameMatch = /^ {2}([a-z0-9-]+):\s*$/.exec(raw);
    if (nameMatch) {
      current = { name: nameMatch[1], group };
      entries.push(current);
      continue;
    }

    const fieldMatch = /^ {4}([a-z_]+):\s*(.*)$/.exec(raw);
    if (fieldMatch && current) current[fieldMatch[1]] = fieldMatch[2].trim();
  }

  // `notes: >` folded text runs on at six spaces; nothing here needs it, so it is dropped
  // rather than half-parsed into something misleading.
  return entries.filter((e) => e.directory);
}

/** Components that are checked out. A missing one is skipped, not an error — `marp clone` owns that. */
export function presentRepos(umbrella = UMBRELLA) {
  return readRegistry(umbrella)
    .map((e) => ({ ...e, path: join(umbrella, e.directory) }))
    .filter((e) => existsSync(join(e.path, '.git')));
}

/** A marked block of one of the umbrella's own files, verbatim, markers included. */
export function umbrellaBlock(file, start, end, umbrella = UMBRELLA) {
  const text = readFileSync(join(umbrella, file), 'utf8');
  const from = text.indexOf(start);
  const to = text.indexOf(end);
  if (from < 0 || to < 0) throw new Error(`${file} is missing its ${start} markers`);
  return text.slice(from, to + end.length);
}

/** The shared instruction block, verbatim, markers included. */
export function sharedBlock(umbrella = UMBRELLA) {
  return umbrellaBlock('AGENTS.md', SHARED_START, SHARED_END, umbrella);
}

/** The README identity block, verbatim, markers included. */
export function brandBlock(umbrella = UMBRELLA) {
  return umbrellaBlock('README.md', BRAND_START, BRAND_END, umbrella);
}

/**
 * The repositories the brand rules apply to.
 *
 * Two are excluded on purpose rather than by oversight. `marp-video-server` is a vendor
 * fork of Jellyfin carrying Jellyfin's own README, and rewriting it would conflict with
 * every upstream sync. `video-processing-gui` is a legacy client that is deliberately
 * branded MARE: it is titled *MARE Video Processing GUI* and links to maregroup.org, and
 * it is not part of a MARP deployment.
 */
export const BRANDED = (umbrella = UMBRELLA) => presentRepos(umbrella)
  .filter((r) => r.name !== 'marp-video-server' && r.name !== 'video-processing-gui');

/** Line endings differ across these repositories; comparing them is never the point. */
export const normalise = (s) => s.replace(/\r\n/g, '\n').trimEnd();

/** Walk a tree, skipping the directories that make a repository-wide scan useless. */
const SKIP = new Set([
  '.git', 'node_modules', '.postgres', 'dist', 'bin', 'obj', 'packages',
  '.vs', '.venv', 'venv', '__pycache__', 'coverage', 'demo', 'test-results',
  'playwright-report', 'old_scripts_for_reference', 'developer',
]);

export function* walk(root, depth = 0) {
  let items;
  try { items = readdirSync(root, { withFileTypes: true }); } catch { return; }
  for (const item of items) {
    if (SKIP.has(item.name)) continue;
    const full = join(root, item.name);
    if (item.isDirectory()) {
      if (depth < 8) yield* walk(full, depth + 1);
    } else if (item.isFile()) {
      try { if (statSync(full).size < 2_000_000) yield full; } catch { /* vanished mid-walk */ }
    }
  }
}
