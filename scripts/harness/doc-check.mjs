/**
 * Catch instruction files that state a fact they cannot keep true, and ones that carry a
 * credential.
 *
 * This exists because of a real incident: the umbrella's `CLAUDE.md` described the
 * development database in two contradictory ways sixty lines apart, an agent resolved the
 * contradiction toward the stale half, and built a plan on it. Prose cannot police itself.
 *
 * Deliberately narrow. A check with false positives teaches everyone to ignore it, so
 * these patterns match what would actually be wrong rather than everything that looks
 * like it might be.
 *
 * Escapes, both as HTML comments so they render as nothing:
 *   <!-- harness:allow -->    on the line, or the line before it
 *   <!-- harness:history -->  anywhere in the file, for the staleness rules only
 *
 * Credentials are never excusable and no escape applies to them.
 */

import { readFileSync } from 'node:fs';
import { relative, resolve, basename } from 'node:path';
import { UMBRELLA, presentRepos, walk, step, ok, fail, warn, dim, red } from './lib.mjs';

/** Instruction files: what a human writes for an agent, plus what an agent is told to copy. */
const INSTRUCTION = /(^|[\\/])(AGENTS|CLAUDE|README|CONTRIBUTING|copilot-instructions)\.md$|\.instructions\.md$|(^|[\\/])\.env\.example$/i;

const RULES = [
  {
    id: 'retired-vm',
    kind: 'stale',
    why: 'names the VirtualBox development environment, which is being retired',
    re: /MARP DEV ENVIRONMENT|VBoxManage|VirtualBox/,
  },
  {
    id: 'stale-db-port',
    kind: 'stale',
    why: 'hard-codes the VM port forward; run `marp db status` instead',
    re: /localhost:5433|DB_PORT\s*=\s*5433/,
  },
  {
    id: 'db-literal',
    kind: 'stale',
    why: 'writes a database host or port into prose; point at `marp db status`',
    re: /DB_(?:HOST|PORT)\s*=\s*(?!replace|\$|\{|<|"?\s*$)[A-Za-z0-9.]/,
  },
  {
    id: 'private-key',
    kind: 'secret',
    why: 'private key material',
    re: /-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\bssh-(?:rsa|ed25519)\s+AAAA/,
  },
  {
    id: 'credential',
    kind: 'secret',
    why: 'looks like a real password, token or key',
    // Placeholders are the common case in these files, so they are excluded by shape
    // rather than by hoping the value looks fake.
    re: /(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*["'`]?(?!replace|your|example|changeme|xxx|<|\$|\{|process\.|null|true|false|["'`]\s*$)[A-Za-z0-9!@#$%^&*()_+=-]{10,}/i,
  },
  {
    id: 'login-pair',
    kind: 'secret',
    why: 'a login and its password, written out',
    // The rule above matches a named field. Credentials in prose often have no field
    // name at all -- a noun like "login" or "credentials", then a user and a secret in
    // backticks -- so that rule alone leaves the commonest shape uncaught, and a check
    // that misses the shape it was written for is worse than no check.
    re: /\b(?:login|credentials?|sign[- ]?in)\b[^\n]{0,24}[:=][^\n]{0,40}`[^`\s]{8,}`/i,
  },
];

const findings = [];

function scan(file, label) {
  let text;
  try { text = readFileSync(file, 'utf8'); } catch { return; }
  if (text.includes('\u0000')) return;   // binary; nothing to read here

  const lines = text.split(/\r?\n/);

  // `harness:history` covers the section it sits in, ending at the next heading of the
  // same or shallower level. Placed before any heading it covers the whole file. A file
  // may legitimately document a retired setup in one section and current practice in
  // another -- marp-api's README is exactly that -- so a file-wide flag is too blunt.
  let headingLevel = 0;
  let historyFrom = null;

  lines.forEach((line, i) => {
    const heading = /^(#{1,6})\s/.exec(line);
    if (heading) {
      headingLevel = heading[1].length;
      if (historyFrom !== null && headingLevel <= historyFrom) historyFrom = null;
    }
    if (line.includes('harness:history')) historyFrom = headingLevel;

    const history = historyFrom !== null;
    const allowed = line.includes('harness:allow') || (lines[i - 1] || '').includes('harness:allow');
    for (const rule of RULES) {
      if (!rule.re.test(line)) continue;
      if (rule.kind === 'stale' && (history || allowed)) continue;
      if (rule.kind === 'secret' && allowed) continue;
      findings.push({
        label, line: i + 1, rule,
        // Never echo the value itself into a log that may be pasted somewhere.
        excerpt: rule.kind === 'secret' ? '(redacted)' : line.trim().slice(0, 96),
      });
    }
  });
}

step('Checking instruction files for stale facts and credentials');

// Explicit paths win over the registry, because CI checks out one component beside the
// umbrella rather than the whole workspace, and the registry would find nothing there.
const explicit = process.argv.slice(2).filter((a) => !a.startsWith('--'));

const components = explicit.length
  ? explicit.map((p) => ({ name: basename(resolve(p)), path: resolve(p) }))
  : presentRepos();

const targets = explicit.length ? components : [{ name: 'MARP', path: UMBRELLA }, ...components];

// The components are checked out *inside* the umbrella, so an unbounded walk from the
// root reports every component file twice, under two names.
const nested = components.map((c) => c.path);
const belongsToAComponent = (file) => nested.some((p) => file.startsWith(p + '\\') || file.startsWith(p + '/'));

for (const repo of targets) {
  if (repo.name === 'marp-video-server') continue;   // outside the harness, see ADR-0006
  let count = 0;
  for (const file of walk(repo.path)) {
    if (!INSTRUCTION.test(file)) continue;
    if (repo.path === UMBRELLA && belongsToAComponent(file)) continue;
    count++;
    scan(file, `${repo.name}/${relative(repo.path, file).replace(/\\/g, '/')}`);
  }
  if (!count) warn(`${repo.name} — no instruction files found`);
}

const secrets = findings.filter((f) => f.rule.kind === 'secret');
const stale = findings.filter((f) => f.rule.kind === 'stale');

for (const f of secrets) {
  fail(`${f.label}:${f.line} — ${red(f.rule.why)}  [${f.rule.id}]`);
}
for (const f of stale) {
  fail(`${f.label}:${f.line} — ${f.rule.why}  [${f.rule.id}]`);
  console.log(`         ${dim(f.excerpt)}`);
}

if (!findings.length) {
  ok('no stale environment facts, no credentials');
  process.exit(0);
}

console.log('');
fail(`${secrets.length} credential finding(s), ${stale.length} stale fact(s)`);
console.log(dim('    Fix, or mark an intentional historical section with <!-- harness:history -->.'));
process.exit(1);
