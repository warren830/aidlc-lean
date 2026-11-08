# AI-DLC Lean v0.2 — design spec (keep AI-DLC's shape, drop the tedium)

Decided with the user on 2026-11-08.

- **Keep** AI-DLC's stage sequence, its artifact names and folders, a record of what each step did, and traceability.
- **Cut**:
  - approval at every stage (only 3 approval points remain);
  - per-stage question files;
  - the 14 personas;
  - per-stage review loops and rituals;
  - long templates (one page per document).

The gate machinery from v0.1 stays: approvals are bound to sha256, the ledger is hash-chained, verify sets the code fingerprint, and the commit gate and records/kit protection are unchanged. Only which artifacts the gates require changes.

## 1. Layout (AI-DLC v1 names; one folder per intent)

```
aidlc-docs/
  lean.json                     config (was aidlc/lean.json)
  audit/<clone-id>.jsonl        hash-chained ledger (was aidlc/audit/)
  contracts/ OWNERS, changes/CR-<team>-<n>-<slug>.md   (multi-team)
  <intent-id>/                  e.g. 261108-marketplace
    aidlc-state.md              stage progress + stage log (generated) + session notes (agent)
    decisions.md                one line per decision
    audit.md                    human-readable audit trail, written by `lean audit pack`
    inception/
      reverse-engineering/architecture.md         optional (brownfield), one page
      requirements/requirements.md                always
      user-stories/stories.md                     optional
      application-design/application-design.md    always, unless skipped (Size: small)
      application-design/unit-of-work.md          optional (multi-team / multi-service)
    construction/
      <unit>/functional-design/functional-design.md           optional
      <unit>/nfr-design/nfr-design.md                         optional (targets + patterns + tech stack)
      <unit>/infrastructure-design/infrastructure-design.md   optional
      plans/<unit>-code-generation-plan.md                    always (checklist of steps)
      build-and-test/build-and-test-summary.md                written by `lean verify`
      build-and-test/evidence/verify-<ts>.md                  regulated mode only
    operations/
      release.md                                              written by `lean release`
```

- `<unit>` is `app` when there is no unit-of-work.md. Otherwise it is each unit name listed in unit-of-work.md.
- The local, gitignored state stays in `.aidlc-lean/`.
- *Changed during implementation: `.aidlc-lean/subagents.json` (see §8.10), what a per-intent audit.md holds (see §8.22), the pstack review brief files (see §8.25).*

## 2. Stages (ids, order, rules)

| # | id | AI-DLC name | file(s) | skippable | approval |
|---|---|---|---|---|---|
| 1 | reverse-engineering | Reverse Engineering | inception/reverse-engineering/architecture.md | yes (greenfield) | – |
| 2 | requirements | Requirements Analysis | inception/requirements/requirements.md | no | **REQUIREMENTS** (or INCEPTION) |
| 3 | user-stories | User Stories | inception/user-stories/stories.md | yes | – |
| 4 | application-design | Application Design | inception/application-design/application-design.md | only if requirements.md says `Size: small` | **DESIGN** (or INCEPTION) |
| 5 | units | Units Generation | inception/application-design/unit-of-work.md | yes | – |
| 6 | functional-design | Functional Design (per unit) | construction/<unit>/functional-design/functional-design.md | yes | – |
| 7 | nfr-design | NFR Requirements + Design (per unit) | construction/<unit>/nfr-design/nfr-design.md | yes | – |
| 8 | infrastructure-design | Infrastructure Design (per unit) | construction/<unit>/infrastructure-design/infrastructure-design.md | yes | – |
| 9 | code-generation | Code Generation (per unit) | construction/plans/<unit>-code-generation-plan.md + code | no | PLAN only in regulated mode |
| 10 | build-and-test | Build and Test | construction/build-and-test/build-and-test-summary.md (tool) | no | – (stops only on failure) |
| 11 | release | Release | operations/release.md (tool) | no | **RELEASE** |

- **Approval kinds** for `request` and approval lines: `REQUIREMENTS`, `DESIGN`, `INCEPTION`, `PLAN`, `RELEASE`, `CR-<team>-<n>`.
  - `INCEPTION` covers requirements.md and application-design.md together. Its hash is sha256 over the concatenation `requirements.md + "\0" + application-design.md`, using whichever of the two exist.
  - `PLAN` is the code-generation plan of a unit, approved per unit: `lean request PLAN --unit <u>`. The approval line stays `approve PLAN <hash>`, and the hash identifies which plan.
  - An approval is still bound to the hash. Any later edit voids it. *(PLAN: ticking steps does not count, see §8.3.)*
- **Code-write gate** (replaces "SPEC approved / PLAN approved"). With an active intent, code writes need:
  1. requirements approved (via REQUIREMENTS or INCEPTION, current hash); and
  2. application design approved (via DESIGN or INCEPTION, current hash), or the application-design stage legitimately skipped (Size: small); and
  3. in regulated mode, the PLAN of the unit approved. If the unit is unknown, require all existing plans to be approved and at least one plan to exist.

  Stale handling is as in v0.1: in standard mode a stale approval is allowed and shown as stale; in regulated mode it blocks. Released intents block code writes (start a new intent). *(Regulated mode only: see §8.8.)* The no-intent behaviour is unchanged: allowed in standard mode, blocked in regulated mode.
- **Commit gate**: unchanged (verify fingerprint).
- **Release**: needs the gate conditions above plus a passing verify on the current fingerprint, as before. *(Changed during implementation: see §8.1 and §8.17.)*

## 3. The per-stage record ("每一步做了什么")

Stage commands are run by the agent itself, with no human stop:

- `lean stage start <id> [--unit U]`
  - creates the stage's document from its template if it is missing (the agent cannot copy templates itself);
  - marks the stage in progress;
  - ledger: `STAGE_STARTED {stage, unit}`.
- `lean stage done <id> [--unit U] --note "<what was done: inputs used, what it produced, key decisions>"`
  - refuses if the stage document is missing or still identical to the template; *(code-generation with unticked steps: see §8.12.)*
  - ledger: `STAGE_COMPLETED {stage, unit, note, outputs: {path: sha256}}`;
  - regenerates aidlc-state.md.
- `lean stage skip <id> [--unit U] --reason "<why>"`
  - refuses for requirements, code-generation, build-and-test and release;
  - refuses application-design unless requirements.md says `Size: small`;
  - ledger: `STAGE_SKIPPED`.
- `lean verify`
  - writes build-and-test-summary.md: commands, exit codes, durations, output digests, fingerprint and protected-file drift; *(base commit and working tree: see §8.16.)*
  - on PASS, also records build-and-test as completed for this fingerprint. *(Shown as done only once every unit's code generation is: see §8.12.)*
- `lean release` writes operations/release.md and records release as in progress. The RELEASE approval completes it. *(See §8.1, §8.17 and §8.18.)*
- Approvals and rejections show in the progress list automatically. *(Also in the Stage log, with refused approval lines: see §8.15 and §8.19.)*

aidlc-state.md (only text between the markers is regenerated; everything else belongs to the agent; *who regenerates it and the list order: see §8.2 and §8.4*):

```
# AI-DLC State: <title>
Intent: <id> · Mode: <standard|regulated|multi-team> · Created: <date>
<!-- lean:begin progress -->
## Stage progress
- [x] Requirements Analysis — approved via INCEPTION (sha 1a2b3c4d) · 2026-11-08
- [S] User Stories — skipped: single persona
- [-] Code Generation (app) — in progress
- [ ] Build and Test
...
## Stage log
### Requirements Analysis · 2026-11-08 10:12 · by dev@corp (team -)
- Did: <note>
- Outputs: inception/requirements/requirements.md (sha 1a2b3c4d)
<!-- lean:end progress -->
## Session notes
Status: ...
### Next
1. ...
### Open questions and blockers
### Notes for the next session
```

- Legend: `[x]` done, `[S]` skipped, `[-]` in progress, `[ ]` not started, `[A]` waiting for approval (the request was printed, no approval yet).
- *Changed during implementation: the `(edited since)` mark (see §8.13), the multi-team `Owner team:` line and `### Next (team <name>)` subsections (see §8.20), the source label at the end of each Stage-log header (see §8.23).*
- The SessionStart and resume context shows the Stage progress lines and the first items of "### Next", within the existing size cap. *(This team's Next first: see §8.20; a subagent's start: see §8.10.)*

## 4. Templates (one page each; in kit/.kiro/aidlc-lean/templates/)

| Template | Contents |
|---|---|
| requirements.md | Size *(a placeholder until written: see §8.9)*, Goal, Not doing, Acceptance criteria table (AC-n), NFR targets, Assumptions (A-n), Questions and answers (one batch, asked in chat and copied here), Contracts touched |
| architecture.md (reverse engineering) | What exists, components, data, integrations, risks, in one page |
| stories.md | personas inline, story table (US-n, AC links) |
| application-design.md | Components and responsibilities, interfaces and methods, dependencies (small diagram), data model, key decisions |
| unit-of-work.md | Unit, owner team, paths, depends on, contracts, stories/ACs, status |
| functional-design.md | Entities, business rules (BR-n), logic and edge cases |
| nfr-design.md | Targets (numbers), patterns, tech-stack decisions |
| infrastructure-design.md | Resources, environments, deployment, cost notes |
| code-generation-plan.md | Ordered checklist of steps (step 1 = walking skeleton), each step naming ACs/BRs and its "done when"; tests mapping AC → test *(ticking: see §8.3 and §8.12)* |
| aidlc-state.md, decisions.md | as above |
| cr.md, lean.json | unchanged from v0.1 |

Each template header names its stage and has HTML-comment hints. "Identical to the template" is checked against the rendered template text.

## 5. Traceability

- IDs: AC-n in requirements, US-n in stories, BR-n in functional design.
- The code-generation plan maps each AC/BR to the test that proves it.
- The build-and-test summary lists the commands that ran.
- No sensor, no extra tool.

## 6. What does not change

- Hooks: SessionStart, UserPromptSubmit, PreToolUse.
- The approval phrase rules.
- protected_paths and "allow test change".
- The deny list, records and kit protection, contracts and CRs, the ledger format, the verify fingerprint, the masking, and the pstack pack mechanics.
- *Changed during implementation: subagent prompts in the hooks (see §8.10), CR scope and `lean cr close` (see §8.11), refused approval lines in the ledger (see §8.15), the pstack review brief (see §8.25).*

Paths move from `aidlc/` to `aidlc-docs/` everywhere: records protection, fingerprint_exclude (still excluding `aidlc-docs/**` except `contracts_dir`), and the docs.

## 7. Steering and skills

- **Steering (always loaded, ≤ 1,000 words)**:
  - the AI-DLC phases and stages, and when to skip one (always with a reason);
  - the 3 approval points;
  - one question batch at the start;
  - one page per document;
  - run `lean stage done` with a note after each stage;
  - never wait for approval except at the 3 points and on failures.
- **Skills (on demand)**:
  - `aidlc-lean-inception`: reverse engineering, requirements, stories, design, units;
  - `aidlc-lean-construction`: the per-unit designs, the code-generation plan and code, verify;
  - `aidlc-lean-release`;
  - `aidlc-lean-resume`;
  - `aidlc-lean-multi-team`;
  - `aidlc-lean-regulated`.

  This replaces aidlc-lean-spec and aidlc-lean-build. Each skill stays ≤ 600 words.

## 8. Changed during implementation (2026-11-08)

Marked here so the sections above stay as agreed. Items 1, 2 and 5 are confirmed by the user (decided 2026-11-08). Item 3 was changed again on 2026-11-08 (PLAN hash without the checkboxes). Items 8 and 9 were decided on 2026-11-08 as well. Items 10 to 25 were decided on 2026-11-08 after the four live runs (docs/e2e-2026-11-08-scenarios.md); they have unit tests only and have not been run in Kiro yet.

1. **Release is tied to the code `lean release` checked.** *(Confirmed, decided 2026-11-08.)* `lean request RELEASE` refuses unless `lean release` would pass now and operations/release.md was written by `lean release` for the current code fingerprint. The prompt hook refuses to record `approve RELEASE` under the same condition. Reason: in a dry run, an agent-written release.md with no passing verify on the merged code was requested, approved, and the intent became released. Side effect: approving RELEASE from another clone needs the same code (same commit, no local product changes). The RELEASE approval also logs `STAGE_COMPLETED {stage: release}`, so Release gets a Stage-log entry like the other stages.
2. **`lean status` writes the generated region of aidlc-state.md** (only between the markers). *(Confirmed, decided 2026-11-08.)* `lean verify` rewrites it too. This brings the page up to date after a pull and clears merge conflicts inside the region (multi-team: run `lean verify`, which also rewrites build-and-test-summary.md). The SessionStart and resume hooks still only read.
3. **Ticking steps keeps a PLAN approval.** *(Changed on 2026-11-08; first implemented as "ticking an approved plan voids it".)* The sha256 a PLAN approval is bound to is taken over the plan with its task checkboxes normalised: in every line that starts with optional whitespace, then `-` or `*`, then ` [x]`, ` [X]` or ` [ ]`, the box counts as ` [ ]`. This hash is used by `lean request PLAN`, by the `approve PLAN` and `reject PLAN` lines, for the approval state and staleness of plan files, in the code-write gate and in the release checks. So ticking or unticking a step keeps the approval; any other edit (a step's text, a new or removed step, the Tests table) voids it, as before. The template and the construction and regulated skills say so. The other pages are still hashed as they are.
4. **Stage progress lists the per-unit stages unit by unit** (each unit's three design stages, then its code generation), as in AI-DLC's per-unit loop. The Stage log stays in recording order, so in multi-team mode the teams' entries interleave.
5. **The Next step follows the stage order.** *(Confirmed, decided 2026-11-08.)* Inception stages without a record first, then unit by unit (designs, plan, PLAN approval in regulated mode, code, `stage done code-generation`), then verify and release. In multi-team mode a clone is pointed only at its own team's units. Guidance only: no gate enforces the order.
6. **Config `plan`**: `auto` means PLAN approvals in regulated mode only, as specified (in v0.1 `auto` also covered multi-team and `Size: large`); `always` requires them in every mode; `never` turns them off.
7. **Approver lists**: an INCEPTION approval must pass the INCEPTION and REQUIREMENTS lists and, when it covers application-design.md, the DESIGN list. A v0.1 `SPEC` list still restricts requirements and design approvals.
8. **A released intent blocks code writes only in regulated mode.** In standard mode a released active intent counts as no active intent, so small edits work as the steering says. In regulated mode code writes stay blocked until a new intent is started (`lean new <slug>`). `lean status` and the SessionStart context say that the active intent is released and that new work needs `lean new`. Stage commands still refuse a released intent.
9. **The requirements template says `Size: <small|large>`**, not `Size: small`. The placeholder counts as not small, so `lean stage skip application-design` is refused until someone writes `small`.
10. **Subagent prompts are not human turns.** *(Decided 2026-11-08, after the live runs.)* Kiro 3.1.0 fires the workspace SessionStart and UserPromptSubmit hooks for a subagent it starts, with the parent chat's session_id, and the UserPromptSubmit prompt is the task prompt the agent wrote. So PreToolUse of a delegation tool (`invoke_sub_agent`, `orchestrate_subagent`, or another tool whose name matches sub_agent, delegat, orchestrat or spawn and whose input has a `prompt`) keeps each dispatched prompt's sha256 and first 200 characters as a pending dispatch in `.aidlc-lean/subagents.json` (the newest 50, each dropped after 2 h). A prompt that matches one (same sha256, or starting with those 200 characters) is logged as `SUBAGENT_PROMPT` and the dispatch is removed: no approval, rejection or `allow test change` is read from it, the chat's turn counter and `allow test change` state stay as they are, and nothing is printed. A SessionStart for a chat this clone already knows, while a dispatch from that chat is pending, is logged as `SUBAGENT_START`; it leaves the chat's turn state alone and prints the context under a subagent header. `doctor` still counts only `SESSION_START`. A dispatch that no prompt answers (pstack's reviewers fired no prompt hook in the brownfield run) just expires. Reason: in the regulated, multi-team and multi-day runs the task prompt of Kiro's built-in reviewer (1,717 characters in one run) was logged as the human's turn and reset the turn and `allow test change`; an approval line in it would have been recorded as the human's.
11. **A change request unlocks a contract only for the team that asked, and only while it is open.** *(Decided 2026-11-08, after the live runs.)* The contract gate lets a write to another team's contract path through only when a CR approved by the owner team (as before) lists that path, its `Requested by team` is this clone's team, and it has not been closed. New command `lean cr close <CR-id> --reason "<why>"` logs `CR_CLOSED {id, path, reason, owner_team, requested_by}`; in multi-team mode only the requesting or the owning team may run it. A closed CR cannot be requested or approved again (a refused approval line is logged, §8.15); a further change needs a new CR. `lean status` lists "Change requests involving your team" with their state (open and approved, waiting, stale or rejected, or closed), and audit.md's CR section lists `CR_OPENED` and `CR_CLOSED` with a "State now" line. Within those paths, the multi-team skill says to change only what the CR describes. Reason: in the multi-team run an approved CR unlocked the whole contract file for good and for any team; catalog later added a section to payments' contract that the CR did not describe, and only the release review noticed.
12. **Code generation counts the plan's steps.** *(Decided 2026-11-08, after the live runs.)* The steps are the plan's task checkboxes, counted the way §8.3 normalises them. While a unit's code generation has no `stage done` record and its plan has unticked steps, Next says "continue the code-generation plan of unit <u>: step N of M (<first unticked step>); tick each step when it is done". `lean stage done code-generation` refuses while any step is unticked ("has K unticked step(s) of M (the first: step N, …)"); a step that is no longer needed is a change of the plan (in regulated mode, a new PLAN approval). Build and Test shows `[-] verify PASS on partial code …; code generation not done yet: <units>` until every unit's code generation is recorded, although verify still records each PASS. This refines §8.5. Reason: in the multi-day run, after step 1 of 3 and a passing verify, Next said to record Code Generation and prepare the release, and `stage done code-generation` accepted the plan with unticked steps; in the multi-team run a verify before any code was written showed Build and Test as done.
13. **`(edited since)` works the same for every completed stage.** *(Decided 2026-11-08, after the live runs.)* One helper marks a completed stage `(edited since)` when a file its `stage done` recorded has changed since. `stage done code-generation` now also stores the plan's hash with the checkboxes normalised (§8.3), so ticking or unticking a step is not an edit; the mark compares the plan only, and code changes show under Build and Test. Requirements and application design that are done but not yet requested show the mark too. Running `stage done` again adds a new Stage-log entry and clears it; the construction skill says to do that, with a note on what changed. Reason: in the multi-day run, after the release was rejected and the plan and code changed, the Code Generation row showed no mark; in the regulated run an edited functional design showed the mark, but nobody recorded it again.
14. **Next points to `lean release` once the review is written.** *(Decided 2026-11-08, after the live runs.)* When `construction/build-and-test/review.md` is newer than the last verify (the intent's in any clone, and this clone's) and this clone's last code write the hook let through (now kept as `last_code_write` in `.aidlc-lean/counters.json`), Next says to run `lean release`. Before that it says "review in a new chat or by a subagent that did not write the code, then `lean release`"; this wording replaces "review in a fresh session" in the tool, the steering and the skills. A chat resumed after a break is told "This is the same chat resumed, not a fresh context." Guidance only: no gate checks the review. Reason: in the brownfield run `lean status` still asked for a review after review.md was written; in the multi-day run the resumed old chat took "review in a fresh session" to mean itself.
15. **Refused approval lines are logged.** *(Decided 2026-11-08, after the live runs.)* Every approval line the prompt hook does not record is logged as `APPROVAL_REFUSED {kind, check, reason, words, session, …}`: `check` is target, hash, release, approvers or team; the words are masked and cut to 300 characters; the typed hash and what the approval would have covered are kept. This covers a missing hash in regulated mode, a hash that no longer matches, an approver not on the list, the wrong team for a CR, a release that is not ready, an ambiguous PLAN and a closed CR. The chat messages are unchanged. Refusals show in audit.md under "Approvals and rejections" and in the Stage log (§8.19). A rejection line the hook cannot match is still only answered in the chat. Reason: in the regulated run an `approve INCEPTION` without a hash was refused, as it should be, but left no trace in the trail.
16. **The build-and-test summary names the base commit and the working tree.** *(Decided 2026-11-08, after the live runs.)* build-and-test-summary.md and the regulated evidence file say `- base commit (HEAD at verify time): <sha12> (<branch>)` and `- working tree: clean`, or `N uncommitted product change(s) (the code fingerprint, not the commit, names the verified code)`. Product changes are the files the code fingerprint covers (`git status` with every untracked file, minus record paths and `.aidlc-lean/`). The VERIFY record adds `base_commit`, `branch` and `uncommitted`, and audit.md shows them. Reason: in the regulated and brownfield runs the summary's `commit` line was HEAD at verify time, before the verified code was committed, so it named a commit without that code.
17. **`lean release` refuses uncommitted product changes.** *(Decided 2026-11-08, after the live runs.)* It prints "Not ready to release: commit the verified code first, then run `lean release` (N uncommitted product change(s): …)" and writes nothing. Uncommitted records (by default `aidlc-docs/` except the contracts, and `.kiro/`) do not stop it; every other file does, `.gitignore` included (`lean init` adds `.aidlc-lean/` to it, so commit it after installing). So the `commit` line of release.md holds the verified code. `request RELEASE` and the approval still check the code fingerprint, as in §8.1. Reason: in the multi-team run `lean release` wrote HEAD as the commit while the code was not committed yet, and the agent had to commit and run it again.
18. **release.md marks superseded approvals.** *(Decided 2026-11-08, after the live runs.)* In its Approvals table, an approval whose files are all covered by a later approval is marked `(superseded)`; an INCEPTION approval with only some of its files covered later is marked `(superseded for <files>)`. Reason: in the regulated run the table listed both INCEPTION and both PLAN approvals without saying which were current.
19. **The Stage log lists approvals.** *(Decided 2026-11-08, after the live runs.)* Besides completed and skipped stages, the Stage log lists APPROVED, REJECTED and APPROVAL_REFUSED, all in recording order: `### <KIND (unit)> approved|rejected (sha x) · <when> · by <who> (team t) · human (prompt)` with `- Covers:` (and `- Words:` for a rejection), and `### <KIND> approval refused (typed <hash> | no hash typed) …` with `- Reason:`. The prompt hook regenerates aidlc-state.md after each approval or rejection it logs. Reason: in the multi-day run the Stage log still showed the first, rejected requirements with no sign of the rejection; approvals and rejections were only in the progress list.
20. **Multi-team: the owner team releases, and each team has its own Next.** *(Decided 2026-11-08, after the live runs.)* `lean new` in multi-team mode writes `Owner team: <team>` (the clone's team) after the `Intent:` line of aidlc-state.md and prints that this team reviews and releases the intent. The owner team is read from that line, so a person can edit it to hand the release over; without the line it is the team of the clone that ran `lean new`. In another team's clone, Next adds "release is done by team X" to the wait-for-unit message and, once that team's own work is verified, says "release is done by team X, the intent's owner team (`Owner team:` in aidlc-state.md), in its clone: commit and push this team's work". Guidance only, as in §8.5: the release commands do not check the team (`approvers` can still restrict RELEASE). In the Session notes each team keeps a `### Next (team <name>)` subsection and edits only its own; the SessionStart, resume and `lean status` excerpts show this team's subsection first, then the generic `### Next`, and leave out other teams'. Reason: in the multi-team run Next pointed both clones at `lean release`, and the two teams overwrote each other's hand-over in the shared Session notes.
21. **`lean init --team` in a configured clone says only what changed.** *(Decided 2026-11-08, after the live runs.)* Where lean.json already exists (a teammate's clone), `lean init --team X` prints "This clone (<id>) is now team X (was Y).", and the advice to set `checks` or `protected_paths` only for those still empty. The INIT record has the team. install.sh still prints its own setup steps on every run. Reason: in the multi-team run the second clone's `init --team` told the user to set `checks`, which were already set.
22. **audit.md for one intent holds only that intent.** *(Decided 2026-11-08, after the live runs.)* A per-intent `lean audit pack` takes the intent's own events, the contract change request events (`CR_OPENED`, `CR_CLOSED`, and the requests, approvals, rejections and refusals of `CR-<team>-<n>`) and the `use` switches from or to the intent; it takes `SESSION_START`, `SUBAGENT_START` and `SUBAGENT_PROMPT` only between the intent's `INTENT_CREATED` and its RELEASE approval, inclusive. Events with no intent, such as a verify run before the intent began, are left out. A pack with no intent still takes everything. audit.md has new sections "Human turns" and "Subagents and host prompts (not the human)". Reason: in the multi-team run the pack counted the setup verify from before the intent.
23. **Each entry says who recorded it.** *(Decided 2026-11-08, after the live runs.)* Each Stage-log header and audit.md row ends with its source: `human (prompt)` for what the prompt hook took from the human's own message (human turns, approvals, rejections, refused approvals, and the Release record the RELEASE approval writes); `via CLI` for the tool's commands, run by the agent or a person in that clone; `hook (session start | subagent start | subagent prompt | host prompt | agent tool call)` for the other hook entries. audit.md explains the labels. The person shown is still the clone's git identity; the label names the channel. Reason: in the brownfield run the agent's stage, verify and release entries and the human's approvals carried the same identity, so the log did not show who did what.
24. **`lean request` reminds the agent of the Session notes.** *(Decided 2026-11-08, after the live runs.)* For every kind except CRs, `lean request` prints "Reminder: the Session notes in aidlc-docs/<intent>/aidlc-state.md are still the template: update the Session notes before you stop (Status, Next)." while the Session notes (from `## Session notes` on, outside the generated region) still match the rendered template, whatever date it was rendered on. Reason: in the multi-team, multi-day and brownfield runs the Session notes stayed the template through Inception.
25. **pstack-interrogate writes its brief to a file.** *(Decided 2026-11-08, after the live runs.)* The lead writes one brief for both reviewers to `aidlc-docs/<intent>/construction/build-and-test/review-brief.md` (the reviewer-prompt template filled in: the intent, the full diff with the acceptance-criteria table and any test output the reviewers need, the rubric with the AI-DLC Lean lens, the code-quality guide), does not change it after the dispatch, and commits it with review.md. It then dispatches `lean-reviewer-opus` and `lean-reviewer-k3` in one message, each with the same short prompt that names the file. pstack-swarm does the same with `aidlc-docs/<intent>/construction/swarm/brief.md` and one short prompt per worker (the path plus its slice). The reviewer and worker cards say to read a named brief file first. Models and read-only tools are unchanged. The same change adds an "Out-of-design changes" section to review.md, where the lead lists changes to interfaces, fields or behaviour that the design pages do not describe. Reason: in the brownfield run each prompt carried the 37 KB brief; Kiro starts a subagent only after its call is written out in full, so the K3 reviewer started 69 s late and the two overlapped for only 44 s. The live run also missed an undesigned `can_review` field.
