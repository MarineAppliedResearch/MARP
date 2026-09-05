/**
 * Claude Code PreToolUse hook: stop the commands that cannot be undone.
 *
 * Permission rules in settings.json match tool names and simple prefixes; the commands
 * worth stopping here are distinguished by their arguments, which is why this is a script.
 *
 * `ask` rather than `deny` for most of it. These are things a human may well want done —
 * pushing, opening a pull request, migrating — and the harness's position is that they are
 * human decisions, not forbidden ones. The genuinely irreversible few are denied outright.
 *
 * Fails OPEN on any error, for the reason spec-gate does.
 */

import { readFileSync } from 'node:fs';

const respond = (decision, reason) => {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: decision, permissionDecisionReason: reason },
  }));
  process.exit(0);
};

/** Denied: no phrasing of these is routine, and the damage is not recoverable. */
const DENY = [
  [/\bgit\s+push\b[^\n]*\s(--force\b|-f\b)/, 'force push — rewrites history other clones and open PRs depend on'],
  [/\bgit\s+push\b[^\n]*\s--delete\b|\bgit\s+push\s+\S+\s+:\S/, 'deleting a remote branch'],
  [/\bgit\s+branch\s+-D\b/, 'force-deleting a branch'],
  [/\bgit\s+reset\s+--hard\b[^\n]*\borigin\//, 'discarding local work against a remote'],
  [/\bmare_v1\b/, 'reaches the production database, which is a scientific record'],
  [/\b(?:systemctl|service)\s+\S*\s*(?:stop|restart|disable)\s+jellyfin(?!-dev)/, 'the live Jellyfin service'],
  [/:8096\b/, 'port 8096 is the live Jellyfin instance; the development one is a different port'],
  [/\bretired-migrations\b/, 'restoring a retired migration breaks every fresh database'],
];

/** Asked: legitimate, and a gate in the workflow rather than a hazard. */
const ASK = [
  [/\bgit\s+push\b/, 'pushing a branch'],
  [/\bgh\s+pr\s+create\b/, 'opening a pull request — this is gate G5, and it is the human\'s call'],
  [/\bsequelize(?:-cli)?\b[^\n]*\bdb:migrate\b/, 'running migrations — confirm the target is a local disposable database'],
  [/\bnpm\s+(?:i|install|add)\s+(?!$)(?!.*--?(?:dry-run|help))\S/, 'adding a dependency'],
  [/\bgit\s+commit\b[^\n]*--amend\b/, 'amending a commit'],
];

try {
  const raw = readFileSync(0, 'utf8');
  const payload = raw.trim() ? JSON.parse(raw) : {};
  const command = payload.tool_input?.command || '';
  if (!command) respond('allow', 'nothing to inspect');

  for (const [pattern, why] of DENY) {
    if (pattern.test(command)) {
      respond('deny',
        `Blocked: ${why}.\n\n` +
        'AGENTS.md lists this under "never without the human present". If it is genuinely\n' +
        'what is wanted, ask them to run it themselves rather than looking for another\n' +
        'phrasing of the same command.');
    }
  }

  for (const [pattern, why] of ASK) {
    if (pattern.test(command)) respond('ask', why);
  }

  respond('allow', 'no dangerous pattern matched');
} catch (error) {
  respond('allow', `gate error, failing open: ${error.message}`);
}
