---
inclusion: always
---
# AI-DLC Lean — how work runs in this repo

This repo uses AI-DLC Lean: AI-DLC's phases, stages, file names and traceability, with few approvals and one page per document. Hooks check the gates; the rules apply even where no hook stops you. Reply in the user's language.

## The tool

`lean` means `python3 .kiro/aidlc-lean/aidlc_lean.py`.

- `lean status`: where the intent stands, what comes next; run it when unsure.
- `lean new <slug> [--title "<title>"] [--ideation]`: start and activate an intent (`aidlc-docs/<yymmdd>-<slug>/`).
- `lean use <intent>`: switch the active intent (logged).
- `lean stage start <id> [--unit U]`: mark a stage in progress and create its page (never copy templates yourself).
- `lean stage done <id> [--unit U] --note "<inputs used, outputs, key decisions>"`: record the stage; refused while its page is missing or still the template.
- `lean stage skip <id> [--unit U] --reason "<why>"`: skip a stage; `ideation` or `operations` skips that phase's unrecorded stages.
- `lean request IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>`: print an approval request; show the human its exact line.
- `lean verify`: run the checks; writes `build-and-test-summary.md`. Nothing is done until it passes on the final code.
- `lean cr new <slug> --owner <team> --paths <p1,p2>`: ask a team to change a contract it owns.
- `lean release`: write `operations/release.md` once approvals and verify are green.
- `lean audit pack`: write the intent's `audit.md` (regulated work).

Never run `lean hook ...`. Never write, by any route, `aidlc-docs/audit/`, `.aidlc-lean/`, `aidlc-docs/lean.json`, the contracts `OWNERS` file or the kit under `.kiro/`; never edit what the tool writes (`build-and-test-summary.md`, evidence, `audit.md`, the progress region of `aidlc-state.md`). Commit `aidlc-docs/`, ledger included, with the code (`git add -A`). Commits changing only `aidlc-docs/` or `.kiro/` (contracts excepted) need no verify; any other needs `lean verify` green first, run as its own command (not chained with `git commit`).

## When to use the flow

- Small, low-risk edits (typo, config value, one-file fix, questions): just do them, no intent (not in regulated mode).
- Anything a reviewer would call a feature or behaviour change: start an intent.

## Phases and stages

Pass `--unit <unit>` to stages 6–9 (`app` unless `unit-of-work.md` lists units).

**Ideation** (optional, `lean new <slug> --ideation`; skill `aidlc-lean-ideation`): `intent-capture`, `market-research`, `feasibility`, `scope-definition`, `team-formation`, `rough-mockups`, `approval-handoff`. Once used, intent capture, scope definition and approval handoff must be recorded done.

**Inception** (what and why; skill `aidlc-lean-inception`):

1. `reverse-engineering`: brownfield only.
2. `requirements`: always.
3. `user-stories`: several user types or changed user-facing flows.
4. `application-design`: always, unless requirements.md says `Size: small`.
5. `units`: work split across teams or services.

**Construction** (how; skill `aidlc-lean-construction`), one unit at a time:

6. `functional-design`: new entities or business rules.
7. `nfr-design`: new NFR targets or tech-stack choices.
8. `infrastructure-design`: new or changed infrastructure.
9. `code-generation`: the unit's plan, then the code. Always.
10. `build-and-test`: `lean verify`, once all units are built. Always.
11. `ci-pipeline`: when CI is new or changes (skill `aidlc-lean-operations`).

**Release** (skill `aidlc-lean-release`):

12. `release`: review in a new chat or by a subagent that did not write the code, `lean release`, RELEASE approval. Always.

**Operations** (optional, before or after RELEASE; skill `aidlc-lean-operations`): `deployment-pipeline`, `environment-provisioning`, `deployment-execution`, `observability-setup`, `incident-response`, `performance-validation`, `feedback-optimization`. Write documents and config; never deploy (the team's CI/CD does).

Go in order; skip a conditional stage that does not apply or adds nothing (`lean stage skip`, with a real reason).

After each stage, run `lean stage done` with its note (`lean verify` and the RELEASE approval record their own), then go straight on without asking.

## Questions and pages

- At the start, read the code, then ask what it cannot answer in ONE numbered batch, each with your recommended answer. Copy them, answered, into requirements.md; what you still guess becomes an assumption (A-1…). Later, ask only what blocks you.
- One page per document, AI-DLC file names, no boilerplate; prefer tables and lists.
- Trace with IDs: AC-n (requirements), US-n (stories), BR-n (functional design). Each code-generation plan maps every AC and BR to its test.
- One line per real decision in `decisions.md`.
- Keep the Session notes in `aidlc-state.md` current at every pause (skill `aidlc-lean-resume`).

## The only human stops

Each approval: `lean request <KIND>`, then wait.

1. **IDEATION**, only with Ideation: once the initiative brief is done.
2. **INCEPTION** (requirements.md and application-design.md together) when the Inception pages are done, or REQUIREMENTS then DESIGN if the human wants two steps.
3. **PLAN**, regulated mode only: `--unit <unit>`, before each unit's code.
4. **RELEASE**: after the review and `lean release`.
5. **Failures**: a check still red after 2–3 fix attempts, a gate you cannot satisfy, a blocking question.

Write no code for an intent before its requirements and design are approved (or design skipped as small), plus IDEATION when used. Only the approval line the human types themselves counts: never approve for them, and never call something approved unless `lean status` shows it. Editing an approved page voids its approval. A released intent takes no more code: start a new one.

## Gates and hooks

- Lines beginning `[AI-DLC Lean]` come from the hooks, not the user.
- Hooks gate code writes on the approvals and commits on verify, and block edits to protected tests, other teams' contracts, records and kit files, and denied commands.
- A blocked call returns `[AI-DLC Lean] blocked (<gate>): <reason>`. Do what the reason says; never try another route around a gate (shell redirection, other tools, subagents, scripts). If a gate seems wrong, tell the human.
- Never weaken, skip or delete tests, or remove authentication, authorization or validation, to get green.
- Acceptance tests under `protected_paths` change only after the human types `allow test change`; that lasts until their next message.

## Modes (set in `aidlc-docs/lean.json`)

- **regulated**: skill `aidlc-lean-regulated`. Every code change needs an intent, approvals carry the hash, stale approvals block, PLAN per unit, verify writes evidence.
- **multi-team**: skill `aidlc-lean-multi-team`. Contracts belong to teams; changing another team's needs their approved change request.
- **Multi-day work** (any mode): skill `aidlc-lean-resume`.
