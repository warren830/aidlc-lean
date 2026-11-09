---
name: aidlc-lean-regulated
description: Use in AI-DLC Lean regulated mode - what is stricter (hash-bound approvals, stale blocks, PLAN per unit, evidence), what the audit trail records, approver identity, and audit.md via lean audit pack.
---
# Regulated mode

## What is stricter
- Every code change needs an active intent with approved requirements and design (INCEPTION, or REQUIREMENTS and DESIGN; design may be skipped only as `Size: small`), IDEATION when Ideation is used, and the unit's approved code-generation plan. Never suggest a change outside the flow: offer a new intent.
- **PLAN per unit**: once `construction/plans/<unit>-code-generation-plan.md` is written, run `lean request PLAN --unit <unit>` and wait for `approve PLAN <hash>` (the hash identifies the plan). For a file in no known unit, at least one plan must exist and all must be approved.
- **The hash is required**: an approval must quote the `lean request` hash, e.g. `approve INCEPTION 1a2b3c4d`.
- **Stale blocks**: a page edited after its approval is stale and blocks code writes until approved again; in a plan, ticking a step keeps the approval, editing a step's text voids it.
- **Evidence**: `lean verify` also writes `construction/build-and-test/evidence/verify-<ts>.md`: commands, exit codes, output digests and tails. Common secret shapes are masked (values of keys named like password, secret, token or credential; Authorization and Bearer headers; URL passwords; GitHub, AWS and Slack tokens; PEM keys), but a secret with no telling name or prefix is not, so keep checks from printing secrets. The verify record keeps the evidence file's sha256.
- Commits and `lean release` need checks configured; commits also need a green verify on the exact code being committed.
- A hook script error blocks tool calls instead of letting them through: run `lean doctor`, fix it, never bypass it.
- **Approvers**: `approvers` in `aidlc-docs/lean.json` can restrict, by git email, who may approve each kind (IDEATION, REQUIREMENTS, DESIGN, INCEPTION, PLAN, RELEASE, CR).

## What the trail contains (`aidlc-docs/audit/<clone>.jsonl`, hash-chained, committed)
- Sessions and every human turn (a hash, not the text); subagent task prompts are logged apart, never as human turns.
- Approval requests; approvals and rejections with the exact words, the hash of the approved page, who and when; refused approval lines (APPROVAL_REFUSED) with the reason.
- Stage records: started, done (with the note and each output's sha256), skipped (with the reason).
- Blocked attempts, and protected-file changes a human allowed.
- Verify runs with a code fingerprint and the evidence file's sha256.
- Contract change requests (opened, approved, closed), and intent switches (`lean use`).

The tool writes the ledger, build-and-test-summary.md, the evidence files and audit.md. Never write or edit any of them.

## Approver identity, honestly
The trail records the git user, the OS user and the host. These are self-asserted, so pair them with Git-server controls:
- a protected main branch;
- merge-request approvals by the named approvers;
- signed commits if the organisation requires them.

If approvals arrive through a chat bridge (Feishu, Jira), the bridge must verify the person and pass the hash. The kit records the bridge's `(via …)` note as a claimed channel.

## At release
1. Before `lean request RELEASE`, run `lean audit verify`: every ledger chain must be OK. It also fails when the ledger files are missing.
2. Once RELEASE is approved, run `lean audit pack`: it writes the intent's `audit.md`, the readable trail (integrity, stages, approvals, human turns, verify runs, blocks, protected changes, CRs, intent switches, sessions, subagents).
3. Commit `aidlc-docs/` (ledger, evidence, audit.md, release.md) together with the code.

Do not put secrets, customer data or credentials in any page. The trail is committed to git.
