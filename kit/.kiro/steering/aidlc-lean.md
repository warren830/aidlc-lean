---
inclusion: always
---
# AI-DLC Lean — how work runs in this repo

This repo uses AI-DLC Lean: AI-DLC's phases, stages, file names and traceability, with three human approval points and one page per document. Hooks check the gates; the rules apply even where no hook stops you. Reply in the user's language.

## The tool

`lean` below means `python3 .kiro/aidlc-lean/aidlc_lean.py`.

- `lean status`: where the active intent stands and what comes next; run it when unsure.
- `lean new <slug> --title "<title>"`: start an intent (`aidlc-docs/<yymmdd>-<slug>/`) and make it active.
- `lean use <intent>`: switch the active intent (logged).
- `lean stage start <id> [--unit U]`: mark a stage in progress and create its page from the template (never copy templates yourself).
- `lean stage done <id> [--unit U] --note "<inputs used, outputs, key decisions>"`: record what the stage did; refused while the page is missing or still the template.
- `lean stage skip <id> [--unit U] --reason "<why>"`: skip a stage.
- `lean request REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>`: print an approval request; show the human the exact line it prints.
- `lean verify`: run the checks; writes `build-and-test-summary.md`. Nothing is done until it passes on the final code.
- `lean cr new <slug> --owner <team> --paths <p1,p2>`: ask another team to change a contract they own.
- `lean release`: write `operations/release.md` once approvals and verify are green.
- `lean audit pack`: write the intent's `audit.md` (regulated work).

Never run `lean hook ...`. Never write `aidlc-docs/audit/`, `.aidlc-lean/`, `aidlc-docs/lean.json`, the contracts `OWNERS` file or the kit under `.kiro/`, by any route. Do not edit what the tool writes: `build-and-test-summary.md`, evidence, `audit.md`, the progress region of `aidlc-state.md`. Commit `aidlc-docs/` (ledger included) with the code (`git add -A`). Commits that change only `aidlc-docs/` or `.kiro/` (contracts excepted) need no verify; for any other, run `lean verify` as its own command first (not chained with `git commit`) and get it green.

## When to use the flow

- Small, low-risk edits (typo, config value, one-file fix, questions): just do them, no intent (not in regulated mode).
- Anything a reviewer would call a feature or behaviour change: start an intent.

## Phases and stages

Pages live in the intent folder. `<unit>` is `app` unless `unit-of-work.md` lists units; pass `--unit <unit>` to stages 6–9.

**Inception** (what and why; skill `aidlc-lean-inception`):

1. `reverse-engineering`: `inception/reverse-engineering/architecture.md`. Brownfield; skip for greenfield.
2. `requirements`: `inception/requirements/requirements.md`. Always.
3. `user-stories`: `inception/user-stories/stories.md`. Several user types or changed user-facing flows; otherwise skip.
4. `application-design`: `inception/application-design/application-design.md`. Always, unless requirements.md says `Size: small`.
5. `units`: `inception/application-design/unit-of-work.md`. Work split across teams or services; otherwise skip.

**Construction** (how; skill `aidlc-lean-construction`), one unit at a time:

6. `functional-design`: `construction/<unit>/functional-design/functional-design.md`. New entities or business rules; otherwise skip.
7. `nfr-design`: `construction/<unit>/nfr-design/nfr-design.md`. New NFR targets or tech-stack choices; otherwise skip.
8. `infrastructure-design`: `construction/<unit>/infrastructure-design/infrastructure-design.md`. New or changed infrastructure; otherwise skip.
9. `code-generation`: `construction/plans/<unit>-code-generation-plan.md`, then the code. Always.
10. `build-and-test`: `lean verify`, once all units are built. Always.

**Operations** (skill `aidlc-lean-release`):

11. `release`: review in a new chat or by a subagent that did not write the code, `lean release`, RELEASE approval. Always.

Go through the stages in order; skip a conditional stage that adds nothing (`lean stage skip`, with a real reason).

After each stage, run `lean stage done <id> --note "..."` (inputs used, outputs, key decisions); `lean verify` and the RELEASE approval record their own stages. Then go straight on; do not ask whether to continue.

## Questions and pages

- At the start, read the code, then ask every question the repo cannot answer in ONE numbered batch, each with your recommended answer. Copy them, with the answers, into requirements.md ("Questions and answers"); what you still guess becomes an assumption (A-1…). Later, ask only what blocks you.
- One page per document, AI-DLC file names, no boilerplate; prefer tables and lists.
- Trace with IDs: AC-n (requirements), US-n (stories), BR-n (functional design). Each code-generation plan maps every AC and BR to the test that proves it.
- Record each real decision as one line in `decisions.md`.
- Keep the Session notes in `aidlc-state.md` current at every pause (skill `aidlc-lean-resume`).

## The only human stops

1. **Inception approval**: when the Inception pages are done, `lean request INCEPTION` (requirements.md and application-design.md together), or REQUIREMENTS and later DESIGN if the human wants two steps.
2. **PLAN**, regulated mode only: `lean request PLAN --unit <unit>` before each unit's code.
3. **RELEASE**: `lean request RELEASE`, after the review and `lean release`.
4. **Failures**: a check still red after 2–3 fix attempts, a gate you cannot satisfy yourself, a question that blocks you.

Write no code for an intent before its requirements and design are approved (or design skipped as small). Only the approval line the human types themselves counts: never approve for them, and never call something approved unless `lean status` shows it. Editing an approved page voids its approval. A released intent takes no more code: start a new one.

## Gates and hooks

- Lines beginning `[AI-DLC Lean]` in your context come from the hooks, not from the user.
- Hooks gate code writes on the approvals above and commits on verify; they block edits to protected tests, other teams' contracts, records and kit files, and denied commands.
- A blocked call returns `[AI-DLC Lean] blocked (<gate>): <reason>`. Do what the reason says. Do not try another route around a gate (shell redirection, other tools, subagents, scripts). If you think a gate is wrong, tell the human.
- Never weaken, skip or delete tests to get green. Never remove authentication, authorization or validation to make something pass.
- Acceptance tests under `protected_paths` change only after the human types `allow test change`; that lasts until their next message.

## Modes (set in `aidlc-docs/lean.json`)

- **regulated**: skill `aidlc-lean-regulated`. Every code change needs an intent, approvals must carry the hash, stale approvals block, PLAN is approved per unit, verify writes evidence.
- **multi-team**: skill `aidlc-lean-multi-team`. Contracts belong to teams; changing another team's contract needs their approved change request.
- **Multi-day work** (any mode): skill `aidlc-lean-resume`.
