/**
 * The G1 gate: refuse implementation while a blocking assumption is unanswered.
 *
 * This is the one check the whole harness turns on. Everything else in AGENTS.md is a
 * rule an agent may or may not honour; this one stops the edit.
 *
 * Usage:
 *   node spec-check.mjs [dir]        report on the repository at dir (default: cwd)
 *   node spec-check.mjs --json       machine-readable, for a Claude Code hook
 *   node spec-check.mjs --require    a missing spec is a failure, not a pass
 *
 * Exit 0 = clear to implement. Exit 1 = a blocking assumption is open, or the spec is
 * malformed. Exit 2 = asked to require a spec and there is none.
 */

import { readFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { step, ok, fail, warn, dim, normalise } from './lib.mjs';

const args = process.argv.slice(2);
const json = args.includes('--json');
const require_ = args.includes('--require');
const dir = resolve(args.find((a) => !a.startsWith('--')) || process.cwd());
const specPath = join(dir, '.marp', 'task.md');

/**
 * Assumptions are checklist items carrying their category and whether they block.
 * The shape is fixed because a checker parses it:
 *
 *   - [ ] **A3 · schema · blocking** — the question
 */
const ITEM = /^\s*-\s*\[( |x|X)\]\s*\*\*\s*([A-Za-z]+\d+)\s*(?:[·|-]\s*([a-z/-]+))?\s*(?:[·|-]\s*(blocking|non-blocking))?\s*\*\*\s*(?:[—-]\s*)?(.*)$/;

function parse(text) {
  const lines = normalise(text).split('\n');
  const front = {};
  const assumptions = [];
  const requirements = [];
  let section = null;

  // Front matter, if present. Only the flat scalars matter here.
  let i = 0;
  if (lines[0]?.trim() === '---') {
    for (i = 1; i < lines.length && lines[i].trim() !== '---'; i++) {
      const m = /^([a-z_]+):\s*(.*)$/.exec(lines[i]);
      if (m) front[m[1]] = m[2].trim();
    }
    i++;
  }

  for (; i < lines.length; i++) {
    const heading = /^##\s+(.*)$/.exec(lines[i]);
    if (heading) { section = heading[1].trim().toLowerCase(); continue; }

    if (section === 'open assumptions') {
      const m = ITEM.exec(lines[i]);
      if (m) {
        assumptions.push({
          id: m[2],
          category: m[3] || 'uncategorised',
          blocking: (m[4] || 'blocking') === 'blocking',
          answered: m[1].toLowerCase() === 'x',
          text: m[5].trim(),
          line: i + 1,
        });
      } else if (/^\s*-\s*\[/.test(lines[i])) {
        // A checklist item that does not parse is worse than none: it looks answered.
        assumptions.push({ malformed: true, raw: lines[i].trim(), line: i + 1 });
      }
    }

    if (section === 'requirements') {
      const m = /^\s*(?:-\s*)?\*\*\s*(R\d+)\s*\*\*\s*(?:[—-]\s*)?(.*)$/.exec(lines[i]);
      if (m) requirements.push({ id: m[1], text: m[2].trim(), line: i + 1 });
    }
  }

  return { front, assumptions, requirements };
}

function report(result) {
  if (json) {
    console.log(JSON.stringify(result));
    return;
  }

  if (!result.spec) {
    if (result.status === 'missing-required') fail(`no .marp/task.md in ${dir}`);
    else warn(`no .marp/task.md — not a task branch, nothing to gate ${dim('(--require to insist)')}`);
    return;
  }

  step(`spec ${result.front.task || '(untitled)'} — ${result.front.status || 'no status'}`);

  for (const a of result.malformed) {
    fail(`line ${a.line}: assumption does not parse, so it cannot be checked`);
    console.log(`         ${dim(a.raw)}`);
  }
  for (const a of result.open) {
    fail(`${a.id} · ${a.category} · blocking — unanswered`);
    console.log(`         ${dim(a.text.slice(0, 100))}`);
  }

  const answered = result.assumptions.filter((a) => a.answered && !a.malformed).length;
  const nonBlocking = result.assumptions.filter((a) => !a.answered && !a.blocking && !a.malformed).length;

  if (answered) ok(`${answered} assumption${answered === 1 ? '' : 's'} answered`);
  if (nonBlocking) warn(`${nonBlocking} open, not blocking`);
  if (result.requirements.length) ok(`${result.requirements.length} numbered requirements`);

  if (result.passed) ok('clear to implement');
  else fail('blocked at G1 — answer the assumptions above before implementing');
}

if (!existsSync(specPath)) {
  const result = {
    spec: false,
    passed: !require_,
    status: require_ ? 'missing-required' : 'no-spec',
    reason: require_ ? 'no .marp/task.md' : 'not a task branch',
  };
  report(result);
  process.exit(require_ ? 2 : 0);
}

const parsed = parse(readFileSync(specPath, 'utf8'));
const malformed = parsed.assumptions.filter((a) => a.malformed);
const open = parsed.assumptions.filter((a) => !a.malformed && a.blocking && !a.answered);
const passed = malformed.length === 0 && open.length === 0;

report({
  spec: true,
  passed,
  path: specPath,
  front: parsed.front,
  assumptions: parsed.assumptions,
  requirements: parsed.requirements,
  malformed,
  open,
  reason: passed
    ? 'no blocking assumptions open'
    : `${open.length} blocking assumption(s) open, ${malformed.length} malformed`,
});

process.exit(passed ? 0 : 1);
