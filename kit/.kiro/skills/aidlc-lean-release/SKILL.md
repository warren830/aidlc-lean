---
name: aidlc-lean-release
description: Use when an AI-DLC Lean intent is built and verified - the review by a context that did not write the code (optionally with pstack-interrogate), lean release, and the RELEASE approval.
---
# Release (stage `release`): review, record, approval

## 1. Review by a context that did not write the code
Review in a new chat, or by a subagent that did not write the code. A resumed chat, even after a long break, is not a new context. In multi-team mode the intent's owner team (`Owner team` in aidlc-state.md) runs the review and the release. The review reads the intent's requirements.md, application-design.md (if any), the code-generation plans, and `git diff <base>..HEAD`, where base is the commit before the intent's work. Findings go to `construction/build-and-test/review.md` as a short table: finding, severity, file:line, fix.
- **Preferred**: ask the human to open a new chat (`/chat new`) and say: "Review intent <id> against its requirements, design and plans, using the diff, and write construction/build-and-test/review.md."
- **With the pstack quality pack installed**: load skill `pstack-interrogate` and follow it (one brief file, two read-only reviewers on different models, one verdict in review.md).
- **Otherwise**: hand a subagent only those pages and the diff, with the checklist below.

Checklist:
- Every AC and BR has a test that checks the expected value, not only "no error", and the plans' Tests tables match the real tests.
- Authorization on every new or changed endpoint or action, including admin and maintenance routes. Input validation and limits.
- No secrets, credentials or personal data in code, logs or pages.
- Data migrations are reversible, or the rollback is written down.
- Contract changes match approved CRs (multi-team), and old consumers keep working unless the CR says breaking.
- Non-functional targets are measured or have a test.
- Boundary and very large inputs (e.g. Decimal precision, overflow) fail with the error the requirements name, or work.
- Nothing outside the approved requirements changed without a decisions.md line.

Fix what matters, run `lean verify` again, and note the remaining items in review.md.

## 2. Release record and approval
1. Run `lean release`. It refuses unless IDEATION (when used), requirements and design (unless skipped as small) are approved, and each unit's plan in regulated mode; verify passed on the current code; and no product change is uncommitted (commit first). It writes `operations/release.md` with the commit, the approvals (superseded ones marked) and the verify result. With no checks configured, regulated mode refuses and standard mode records that nothing was verified; tell the human.
2. Fill in its "Open items": unresolved questions, known gaps, follow-ups.
3. Run `lean request RELEASE`, show the human the exact line it prints and wait. The request and the approval count only for the code `lean release` checked: after any code change, or a stage recorded or skipped since, run `lean verify` and `lean release` again.
4. Once approved, update the Session notes in aidlc-state.md (`Status: released`, follow-ups under Next) and commit `aidlc-docs/`, so the ledger carries the approval.

In regulated mode, also run `lean audit verify` before the request and `lean audit pack` after the approval (skill `aidlc-lean-regulated`), and commit the evidence and audit.md with the release.

After the approval the intent is closed (`lean status` shows it released): only its Operations pages and ci-pipeline still take edits and stage commands (skill `aidlc-lean-operations`, or `lean stage skip operations --reason "<why>"`). Design changes, follow-ups and fixes start a new intent (`lean new <slug>`); until then regulated mode blocks code writes, and standard mode allows only small edits.
