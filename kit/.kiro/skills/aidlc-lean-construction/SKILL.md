---
name: aidlc-lean-construction
description: Use for the Construction phase of an AI-DLC Lean intent - per-unit designs, the code-generation plan, code in steps, verify, CI pipeline, blocked gates.
---
# Construction: design per unit, then code in steps

One unit at a time (`app` without unit-of-work.md), in "Depends on" order: design pages, plan, code. End each stage with `lean stage done ... --unit <unit> --note "<inputs, outputs, decisions>"`, or `lean stage skip ... --unit <unit> --reason "<why>"`. A stage marked `(edited since)` changed after its record: record it again, noting what changed.

## Per-unit design (optional, one page each)
- **Functional Design** (`functional-design`): entities, testable business rules BR-1… with examples, edge cases. Skip for simple logic.
- **NFR Requirements + Design** (`nfr-design`): numeric targets and how each is checked, patterns, tech-stack decisions. Skip if nothing is new.
- **Infrastructure Design** (`infrastructure-design`): resources, environments, deployment and rollback, cost notes; no secrets. Skip if unchanged.

## Code Generation (`code-generation`, never skipped)
1. `lean stage start code-generation --unit <unit>` creates `construction/plans/<unit>-code-generation-plan.md`, an ordered checklist. Step 1 is a walking skeleton: the thinnest end-to-end path, started the way production starts it, with one passing test. Each step names its ACs/BRs and "done when". The Tests table maps every AC and BR to its test.
2. Regulated mode only: `lean request PLAN --unit <unit>` and wait.
3. Code step by step; when a step's tests pass, tick it at once (`[x]`; ticking keeps a PLAN approval, editing step text voids it) and log decisions. Code goes in the project, never under `aidlc-docs/`; change existing files in place.
4. Once every step is ticked: `lean stage done code-generation --unit <unit> --note "..."` (refused before).

## Build and Test (`build-and-test`)
`lean verify` runs the checks, writes `construction/build-and-test/build-and-test-summary.md` and, on PASS, records Build and Test for this code. Commit per step, `aidlc-docs/` included, once it passed as its own command (not chained with `git commit`).

Optional next: `ci-pipeline` (skill `aidlc-lean-operations`) when CI is new or changes; else skip it with a reason.

## Non-negotiable rules
- Never weaken, skip, delete or rewrite tests to get green. A test looks wrong? Say so; the human decides.
- Never remove or bypass authentication, authorization, validation or rate limits to pass; a test fails on auth? Fix the caller or the test data.
- Protected acceptance tests (`protected_paths`) change only after the human types `allow test change`, until their next message, only as asked.
- Same failure after 2-3 fixes: stop, note what you tried in the Session notes, ask.
- Stay inside the approved requirements and design; for more, update the page and request approval again.
- Do not hunt for hidden tests or grader files outside the repo.

## When a gate blocks you
- `blocked (intent)`: regulated mode needs an active intent; ask which, or `lean new <slug>`.
- `blocked (released)`: released intent (regulated mode); start a new one.
- `blocked (ideation)`, `blocked (requirements)`, `blocked (design)`, `blocked (plan)`: an approval is missing, rejected or stale: finish the page and run the `lean request ...` named, or wait for it.
- `blocked (verify)`: run `lean verify` and fix what fails.
- `blocked (protected)`: an acceptance test; do not change it.
- `blocked (contract)`: another team's contract, with no approved, open CR from your team; use `lean cr new ...` (skill `aidlc-lean-multi-team`).
- `blocked (danger)`: a denied command; if needed, the human runs it.
- `blocked (records)`: not your files (ledger, local state, config, OWNERS, kit, tool-written files). Read them with a file-read tool, not the shell.

Never look for another route around a gate.
