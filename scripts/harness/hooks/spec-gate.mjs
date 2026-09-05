/**
 * Claude Code PreToolUse hook: refuse to implement while the design is unsettled.
 *
 * This is gate G1 in AGENTS.md, and it is the only mechanism in any of our three tools
 * that can actually stop implementation rather than ask for it. Everything else is a
 * sentence an agent may or may not honour.
 *
 * Reads the hook payload on stdin, writes a permission decision on stdout.
 *
 * Fails OPEN, deliberately and in every failure mode: a missing umbrella, an unreadable
 * spec, a crash in this script. A component is allowed to be cloned standalone, and a
 * broken gate must never look like a broken repository. A gate that blocks work when it
 * malfunctions gets disabled within a day, and then it protects nothing.
 */

import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, dirname, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

const allow = (reason) => {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow', permissionDecisionReason: reason },
  }));
  process.exit(0);
};

const deny = (reason) => {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason },
  }));
  process.exit(0);
};

try {
  const raw = readFileSync(0, 'utf8');
  const payload = raw.trim() ? JSON.parse(raw) : {};
  const projectDir = payload.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();

  const specPath = join(projectDir, '.marp', 'task.md');
  if (!existsSync(specPath)) allow('no .marp/task.md — not a task branch');

  // Editing the spec itself is how the gate is opened; it can never be what the gate
  // blocks. Same for the verification plan and anything else under .marp/.
  const target = payload.tool_input?.file_path || payload.tool_input?.notebook_path || '';
  if (target) {
    const abs = isAbsolute(target) ? target : resolve(projectDir, target);
    const rel = relative(projectDir, abs).replace(/\\/g, '/');
    if (rel.startsWith('.marp/')) allow('editing the task specification');
  }

  const checker = join(dirname(fileURLToPath(import.meta.url)), '..', 'spec-check.mjs');
  if (!existsSync(checker)) allow('harness not present beside this repository');

  const result = spawnSync(process.execPath, [checker, projectDir, '--json'], { encoding: 'utf8' });
  if (result.status === null || !result.stdout) allow('spec check could not run');

  let report;
  try { report = JSON.parse(result.stdout); } catch { allow('spec check produced no verdict'); }

  if (report.passed) allow(report.reason || 'design settled');

  const open = (report.open || []).map((a) => `  ${a.id} · ${a.category} — ${a.text}`).join('\n');
  const malformed = (report.malformed || []).map((a) => `  line ${a.line}: ${a.raw}`).join('\n');

  deny(
    'Blocked at gate G1: the design is not settled.\n\n' +
    (open ? `Unanswered blocking assumptions in .marp/task.md:\n${open}\n\n` : '') +
    (malformed ? `Assumptions that do not parse, so they cannot be checked:\n${malformed}\n\n` : '') +
    'Ask the human these questions and record the answers in .marp/task.md before\n' +
    'implementing. Editing .marp/ is always allowed. If an assumption turns out not to\n' +
    'be material, say so and retag it as non-blocking rather than silently ticking it.'
  );
} catch (error) {
  allow(`gate error, failing open: ${error.message}`);
}
