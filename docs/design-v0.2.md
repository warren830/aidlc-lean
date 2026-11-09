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
- *v0.3 adds `ideation/<stage>/`, `construction/ci-pipeline/` and `operations/<stage>/`, one page each: see §9.1.*

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

*(v0.3: the optional ci-pipeline comes after build-and-test, so the steering numbers it 11 and release 12; Release is a phase of its own, between Construction and Operations, with its file under `operations/`. See §9.1.)*

- **Approval kinds** for `request` and approval lines: `REQUIREMENTS`, `DESIGN`, `INCEPTION`, `PLAN`, `RELEASE`, `CR-<team>-<n>`. *(v0.3 adds `IDEATION`, and 15 optional stages around this table: see §9.)*
  - `INCEPTION` covers requirements.md and application-design.md together. Its hash is sha256 over the concatenation `requirements.md + "\0" + application-design.md`, using whichever of the two exist.
  - `PLAN` is the code-generation plan of a unit, approved per unit: `lean request PLAN --unit <u>`. The approval line stays `approve PLAN <hash>`, and the hash identifies which plan.
  - An approval is still bound to the hash. Any later edit voids it. *(PLAN: ticking steps does not count, see §8.3.)*
- **Code-write gate** (replaces "SPEC approved / PLAN approved"). With an active intent, code writes need:
  1. requirements approved (via REQUIREMENTS or INCEPTION, current hash); and
  2. application design approved (via DESIGN or INCEPTION, current hash), or the application-design stage legitimately skipped (Size: small); and
  3. in regulated mode, the PLAN of the unit approved. If the unit is unknown, require all existing plans to be approved and at least one plan to exist.

  Stale handling is as in v0.1: in standard mode a stale approval is allowed and shown as stale; in regulated mode it blocks. Released intents block code writes (start a new intent). *(Regulated mode only: see §8.8.)* The no-intent behaviour is unchanged: allowed in standard mode, blocked in regulated mode. *(Contract files are code for this gate too: see §8.26.)*
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

- Legend: `[x]` done, `[S]` skipped, `[-]` in progress, `[ ]` not started, `[A]` waiting for approval (the request was printed, no approval yet). *(Changed 2026-11-09: a request whose approval line the prompt hook would refuse now, i.e. REQUIREMENTS or INCEPTION while Ideation is in use and IDEATION does not count yet (§9.2), or RELEASE while `lean release` would not pass (§8.1), is shown as `[-] <stage> — <KIND> requested; the approval waits: <why>`, with no approval line. Second QA round, 2026-11-09: only what every clone sees the same way counts for this row, not this clone's own verify (§8.2). A pending IDEATION gets no line either while a stage it needs was started again (§9.2). Nor does a RELEASE request while its release.md lacks an approval `lean release` would list now (§8.1).)*
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

Each template header names its stage and has HTML-comment hints. "Identical to the template" is checked against the rendered template text. *(v0.3: a re-install keeps the templates a person changed or added; see §9.3.)*

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

  This replaces aidlc-lean-spec and aidlc-lean-build. Each skill stays ≤ 600 words. *(v0.3 adds `aidlc-lean-ideation` and `aidlc-lean-operations`: see §9.3.)*

## 8. Changed during implementation (2026-11-08)

Marked here so the sections above stay as agreed. Items 1, 2 and 5 are confirmed by the user (decided 2026-11-08). Item 3 was changed again on 2026-11-08 (PLAN hash without the checkboxes). Items 8 and 9 were decided on 2026-11-08 as well. Items 10 to 25 were decided on 2026-11-08 after the four live runs (docs/e2e-2026-11-08-scenarios.md); they have unit tests only and have not been run in Kiro yet. Item 26 was decided on 2026-11-09 after the QA review of v0.3 (unit tests only). The notes marked "Second QA round" (here and in §3 and §9) come from the second QA review of v0.3 on 2026-11-09; they have unit tests only too.

1. **Release is tied to the code `lean release` checked.** *(Confirmed, decided 2026-11-08.)* `lean request RELEASE` refuses unless `lean release` would pass now and operations/release.md was written by `lean release` for the current code fingerprint. The prompt hook refuses to record `approve RELEASE` under the same condition. *(Completed 2026-11-09: until then the approval line checked only that release.md was written for the current code; now it also runs the `lean release` checks, so a stale or rejected IDEATION or requirements, a design or plan approval that is not current, or no passing verify refuses it, logged as APPROVAL_REFUSED with check `release`. Meanwhile Stage progress shows `[-] Release — RELEASE requested; the approval waits: not ready to release: …`, with no approval line. That row leaves out this clone's own verify: see §8.2.)* Reason: in a dry run, an agent-written release.md with no passing verify on the merged code was requested, approved, and the intent became released. Side effect: approving RELEASE from another clone needs the same code (same commit, no local product changes) and, when `checks` are set, a passing verify in that clone (a verify counts only in the clone that ran it). The RELEASE approval also logs `STAGE_COMPLETED {stage: release}`, so Release gets a Stage-log entry like the other stages. *(Second QA round, 2026-11-09: an approval or rejection of the intent recorded after `lean release` wrote release.md voids that release.md, because its Approvals table lacks it; RELEASE's own decisions do not count, so after a RELEASE rejection the same release.md may be requested again. The Release row then says ``[-] Release — release.md was written (<date>) before <KIND> approved: run `release` again`` (or `rejected`; a pending request refused for another reason shows that reason first), and Next says to run `lean release` again. `request RELEASE` and the old approval line (check `release`) are refused until a new `lean release`, whose release.md lists the new approval. Reason: re-approving the changed requirements or Ideation pages that had refused an approval line revived the old request, and the intent was released with a release.md that lacked the new approval.)* *(Third QA round, 2026-11-09: the check goes by the content of release.md, not by time or intent tags. release.md is void while its Approvals table lacks an approval `lean release` would list now: every approval of the intent and every CR approval, each matched by its row's sha, approver and record time. The Release row says ``[-] Release — release.md (written <date>) does not list <KIND> approved: run `release` again``. A rejection no longer voids it: the gates refuse a rejected approval anyway. Reason: a CR approved while another intent was active in the approving clone was missed, and a CR approved in a clone whose clock ran 24 h ahead kept even a fresh release.md refused.)* *(Fourth QA round, 2026-11-09: the rows are read from the Approvals section's table only, outside HTML comments, with each cell's whitespace collapsed, so a formatter padding the columns changes nothing and cells written elsewhere do not count. The `lean release` run that wrote release.md is also chosen by content: the run whose recorded sha256 is the file's, else (Open items filled in) one whose code fingerprint is the one the file names, not the latest by the clones' clocks.)*
2. **`lean status` writes the generated region of aidlc-state.md** (only between the markers). *(Confirmed, decided 2026-11-08.)* `lean verify` rewrites it too. This brings the page up to date after a pull and clears merge conflicts inside the region (multi-team: run `lean verify`, which also rewrites build-and-test-summary.md). The SessionStart and resume hooks still only read. *(Second QA round, 2026-11-09: the committed region never depends on one clone's own state, only on what every clone shares, the ledgers and the files; for the same commit and ledgers every clone writes the same region. So a clone without its own passing verify still writes the same `[A] Release — waiting for approval: approve RELEASE <hash>` row. The approval line typed in that clone is refused (`no passing verify on the current code`, §8.1), and its `lean status` Next says to run `lean verify` (when `checks` are set). Reason: the Release row flipped to `[-] … no passing verify on the current code` in a teammate's clone, which then committed it.)* *(Third QA round, 2026-11-09: the Build and Test and Release rows compare the verify and `lean release` fingerprints with the committed code (HEAD's tree, the same record paths left out), not with the working tree, so an untracked file or an uncommitted change in one clone changes no row. Verified code that is not committed yet shows `[-] Build and Test — the committed code is not the code of the last verify PASS …`; before the first commit the working tree counts. Outside the region, `lean status` adds `Working tree: N uncommitted product change(s) (…)`, because verify, the commit gate and the RELEASE approval go by the working tree. Reason: an untracked .DS_Store in a teammate's clone wrote `code changed …` and `release.md is for older code` into the shared page.)* *(Fourth QA round, 2026-11-09: a fingerprint now counts for these two rows when it is the working tree's or the committed code's. So `lean verify` followed by the commit commits a page that says `[x] Build and Test — verify PASS`, and another clone's untracked file or uncommitted edit still changes no row. The `[-] … the committed code is not the code of the last verify PASS` wording is gone; the row says `code changed since the last verify PASS` only when neither matches. Reason: the documented verify-then-commit flow committed a page saying its own code was not verified.)*
3. **Ticking steps keeps a PLAN approval.** *(Changed on 2026-11-08; first implemented as "ticking an approved plan voids it".)* The sha256 a PLAN approval is bound to is taken over the plan with its task checkboxes normalised: in every line that starts with optional whitespace, then `-` or `*`, then ` [x]`, ` [X]` or ` [ ]`, the box counts as ` [ ]`. This hash is used by `lean request PLAN`, by the `approve PLAN` and `reject PLAN` lines, for the approval state and staleness of plan files, in the code-write gate and in the release checks. So ticking or unticking a step keeps the approval; any other edit (a step's text, a new or removed step, the Tests table) voids it, as before. The template and the construction and regulated skills say so. The other pages are still hashed as they are.
4. **Stage progress lists the per-unit stages unit by unit** (each unit's three design stages, then its code generation), as in AI-DLC's per-unit loop. The Stage log stays in recording order, so in multi-team mode the teams' entries interleave.
5. **The Next step follows the stage order.** *(Confirmed, decided 2026-11-08.)* Inception stages without a record first, then unit by unit (designs, plan, PLAN approval in regulated mode, code, `stage done code-generation`), then verify and release. In multi-team mode a clone is pointed only at its own team's units. Guidance only: no gate enforces the order.
6. **Config `plan`**: `auto` means PLAN approvals in regulated mode only, as specified (in v0.1 `auto` also covered multi-team and `Size: large`); `always` requires them in every mode; `never` turns them off.
7. **Approver lists**: an INCEPTION approval must pass the INCEPTION and REQUIREMENTS lists and, when it covers application-design.md, the DESIGN list. A v0.1 `SPEC` list still restricts requirements and design approvals.
8. **A released intent blocks code writes only in regulated mode.** In standard mode a released active intent counts as no active intent, so small edits work as the steering says. In regulated mode code writes stay blocked until a new intent is started (`lean new <slug>`). `lean status` and the SessionStart context say that the active intent is released and that new work needs `lean new`. Stage commands still refuse a released intent, except for the Operations stages and ci-pipeline (v0.3, §9.2).
9. **The requirements template says `Size: <small|large>`**, not `Size: small`. The placeholder counts as not small, so `lean stage skip application-design` is refused until someone writes `small`.
10. **Subagent prompts are not human turns.** *(Decided 2026-11-08, after the live runs.)* Kiro 3.1.0 fires the workspace SessionStart and UserPromptSubmit hooks for a subagent it starts, with the parent chat's session_id, and the UserPromptSubmit prompt is the task prompt the agent wrote. So PreToolUse of a delegation tool (`invoke_sub_agent`, `orchestrate_subagent`, or another tool whose name matches sub_agent, delegat, orchestrat or spawn and whose input has a `prompt`) keeps each dispatched prompt's sha256 and first 200 characters as a pending dispatch in `.aidlc-lean/subagents.json` (the newest 50, each dropped after 2 h). A prompt that matches one (same sha256, or starting with those 200 characters) is logged as `SUBAGENT_PROMPT` and the dispatch is removed: no approval, rejection or `allow test change` is read from it, the chat's turn counter and `allow test change` state stay as they are, and nothing is printed. A SessionStart for a chat this clone already knows, while a dispatch from that chat is pending, is logged as `SUBAGENT_START`; it leaves the chat's turn state alone and prints the context under a subagent header. `doctor` still counts only `SESSION_START`. A dispatch that no prompt answers (pstack's reviewers fired no prompt hook in the brownfield run) just expires. Reason: in the regulated, multi-team and multi-day runs the task prompt of Kiro's built-in reviewer (1,717 characters in one run) was logged as the human's turn and reset the turn and `allow test change`; an approval line in it would have been recorded as the human's.
11. **A change request unlocks a contract only for the team that asked, and only while it is open.** *(Decided 2026-11-08, after the live runs.)* The contract gate lets a write to another team's contract path through only when a CR approved by the owner team (as before) lists that path, its `Requested by team` is this clone's team, and it has not been closed. New command `lean cr close <CR-id> --reason "<why>"` logs `CR_CLOSED {id, path, reason, owner_team, requested_by}`; in multi-team mode only the requesting or the owning team may run it. A closed CR cannot be requested or approved again (a refused approval line is logged, §8.15); a further change needs a new CR. `lean status` lists "Change requests involving your team" with their state (open and approved, waiting, stale or rejected, or closed), and audit.md's CR section lists `CR_OPENED` and `CR_CLOSED` with a "State now" line. Within those paths, the multi-team skill says to change only what the CR describes. *(Since §8.26 an unlocked write then goes through the code-write gates too.)* Reason: in the multi-team run an approved CR unlocked the whole contract file for good and for any team; catalog later added a section to payments' contract that the CR did not describe, and only the release review noticed.
12. **Code generation counts the plan's steps.** *(Decided 2026-11-08, after the live runs.)* The steps are the plan's task checkboxes, counted the way §8.3 normalises them. While a unit's code generation has no `stage done` record and its plan has unticked steps, Next says "continue the code-generation plan of unit <u>: step N of M (<first unticked step>); tick each step when it is done". `lean stage done code-generation` refuses while any step is unticked ("has K unticked step(s) of M (the first: step N, …)"); a step that is no longer needed is a change of the plan (in regulated mode, a new PLAN approval). Build and Test shows `[-] verify PASS on partial code …; code generation not done yet: <units>` until every unit's code generation is recorded, although verify still records each PASS. This refines §8.5. Reason: in the multi-day run, after step 1 of 3 and a passing verify, Next said to record Code Generation and prepare the release, and `stage done code-generation` accepted the plan with unticked steps; in the multi-team run a verify before any code was written showed Build and Test as done.
13. **`(edited since)` works the same for every completed stage.** *(Decided 2026-11-08, after the live runs.)* One helper marks a completed stage `(edited since)` when a file its `stage done` recorded has changed since. `stage done code-generation` now also stores the plan's hash with the checkboxes normalised (§8.3), so ticking or unticking a step is not an edit; the mark compares the plan only, and code changes show under Build and Test. Requirements and application design that are done but not yet requested show the mark too. Running `stage done` again adds a new Stage-log entry and clears it; the construction skill says to do that, with a note on what changed. Reason: in the multi-day run, after the release was rejected and the plan and code changed, the Code Generation row showed no mark; in the regulated run an edited functional design showed the mark, but nobody recorded it again.
14. **Next points to `lean release` once the review is written.** *(Decided 2026-11-08, after the live runs.)* When `construction/build-and-test/review.md` is newer than the last verify (the intent's in any clone, and this clone's) and this clone's last code write the hook let through (now kept as `last_code_write` in `.aidlc-lean/counters.json`), Next says to run `lean release`. Before that it says "review in a new chat or by a subagent that did not write the code, then `lean release`"; this wording replaces "review in a fresh session" in the tool, the steering and the skills. A chat resumed after a break is told "This is the same chat resumed, not a fresh context." Guidance only: no gate checks the review. Reason: in the brownfield run `lean status` still asked for a review after review.md was written; in the multi-day run the resumed old chat took "review in a fresh session" to mean itself.
15. **Refused approval lines are logged.** *(Decided 2026-11-08, after the live runs.)* Every approval line the prompt hook does not record is logged as `APPROVAL_REFUSED {kind, check, reason, words, session, …}`: `check` is target, hash, release, approvers or team (v0.3 adds ideation); the words are masked and cut to 300 characters; the typed hash and what the approval would have covered are kept. This covers a missing hash in regulated mode, a hash that no longer matches, an approver not on the list, the wrong team for a CR, a release that is not ready (release.md not written by `lean release` for the current code, or `lean release` would not pass now: §8.1), an ambiguous PLAN and a closed CR. *(v0.3: also REQUIREMENTS or INCEPTION before IDEATION, check ideation, and IDEATION while a stage it needs is not recorded done, check target: §9.2.)* The chat messages are unchanged. Refusals show in audit.md under "Approvals and rejections" and in the Stage log (§8.19). A rejection line the hook cannot match is still only answered in the chat. Reason: in the regulated run an `approve INCEPTION` without a hash was refused, as it should be, but left no trace in the trail.
16. **The build-and-test summary names the base commit and the working tree.** *(Decided 2026-11-08, after the live runs.)* build-and-test-summary.md and the regulated evidence file say `- base commit (HEAD at verify time): <sha12> (<branch>)` and `- working tree: clean`, or `N uncommitted product change(s) (the code fingerprint, not the commit, names the verified code)`. Product changes are the files the code fingerprint covers (`git status` with every untracked file, minus record paths and `.aidlc-lean/`). The VERIFY record adds `base_commit`, `branch` and `uncommitted`, and audit.md shows them. Reason: in the regulated and brownfield runs the summary's `commit` line was HEAD at verify time, before the verified code was committed, so it named a commit without that code.
17. **`lean release` refuses uncommitted product changes.** *(Decided 2026-11-08, after the live runs.)* It prints "Not ready to release: commit the verified code first, then run `lean release` (N uncommitted product change(s): …)" and writes nothing. Uncommitted records (by default `aidlc-docs/` except the contracts, and `.kiro/`) do not stop it; every other file does, `.gitignore` included (`lean init` adds `.aidlc-lean/` to it, so commit it after installing). So the `commit` line of release.md holds the verified code. `request RELEASE` and the approval still check the code fingerprint, as in §8.1. Reason: in the multi-team run `lean release` wrote HEAD as the commit while the code was not committed yet, and the agent had to commit and run it again.
18. **release.md marks superseded approvals.** *(Decided 2026-11-08, after the live runs.)* In its Approvals table, an approval whose files are all covered by a later approval is marked `(superseded)`; an INCEPTION approval with only some of its files covered later is marked `(superseded for <files>)`. *(v0.3, 2026-11-09: IDEATION is one approval over the whole set of Ideation pages, so a later IDEATION approval of the intent supersedes an earlier one as a whole, even when a page was removed in between.)* Reason: in the regulated run the table listed both INCEPTION and both PLAN approvals without saying which were current.
19. **The Stage log lists approvals.** *(Decided 2026-11-08, after the live runs.)* Besides completed and skipped stages, the Stage log lists APPROVED, REJECTED and APPROVAL_REFUSED, all in recording order: `### <KIND (unit)> approved|rejected (sha x) · <when> · by <who> (team t) · human (prompt)` with `- Covers:` (and `- Words:` for a rejection), and `### <KIND> approval refused (typed <hash> | no hash typed) …` with `- Reason:`. The prompt hook regenerates aidlc-state.md after each approval or rejection it logs. Reason: in the multi-day run the Stage log still showed the first, rejected requirements with no sign of the rejection; approvals and rejections were only in the progress list.
20. **Multi-team: the owner team releases, and each team has its own Next.** *(Decided 2026-11-08, after the live runs.)* `lean new` in multi-team mode writes `Owner team: <team>` (the clone's team) after the `Intent:` line of aidlc-state.md and prints that this team reviews and releases the intent. The owner team is read from that line, so a person can edit it to hand the release over; without the line it is the team of the clone that ran `lean new`. In another team's clone, Next adds "release is done by team X" to the wait-for-unit message and, once that team's own work is verified, says "release is done by team X, the intent's owner team (`Owner team:` in aidlc-state.md), in its clone: commit and push this team's work". Guidance only, as in §8.5: the release commands do not check the team (`approvers` can still restrict RELEASE). In the Session notes each team keeps a `### Next (team <name>)` subsection and edits only its own; the SessionStart, resume and `lean status` excerpts show this team's subsection first, then the generic `### Next`, and leave out other teams'. Reason: in the multi-team run Next pointed both clones at `lean release`, and the two teams overwrote each other's hand-over in the shared Session notes.
21. **`lean init --team` in a configured clone says only what changed.** *(Decided 2026-11-08, after the live runs.)* Where lean.json already exists (a teammate's clone), `lean init --team X` prints "This clone (<id>) is now team X (was Y).", and the advice to set `checks` or `protected_paths` only for those still empty. The INIT record has the team. install.sh still prints its own setup steps on every run. Reason: in the multi-team run the second clone's `init --team` told the user to set `checks`, which were already set.
22. **audit.md for one intent holds only that intent.** *(Decided 2026-11-08, after the live runs.)* A per-intent `lean audit pack` takes the intent's own events, the contract change request events (`CR_OPENED`, `CR_CLOSED`, and the requests, approvals, rejections and refusals of `CR-<team>-<n>`) and the `use` switches from or to the intent; it takes `SESSION_START`, `SUBAGENT_START` and `SUBAGENT_PROMPT` only between the intent's `INTENT_CREATED` and its RELEASE approval, inclusive. Events with no intent, such as a verify run before the intent began, are left out. A pack with no intent still takes everything. audit.md has new sections "Human turns" and "Subagents and host prompts (not the human)". Reason: in the multi-team run the pack counted the setup verify from before the intent.
23. **Each entry says who recorded it.** *(Decided 2026-11-08, after the live runs.)* Each Stage-log header and audit.md row ends with its source: `human (prompt)` for what the prompt hook took from the human's own message (human turns, approvals, rejections, refused approvals, and the Release record the RELEASE approval writes); `via CLI` for the tool's commands, run by the agent or a person in that clone; `hook (session start | subagent start | subagent prompt | host prompt | agent tool call)` for the other hook entries. audit.md explains the labels. The person shown is still the clone's git identity; the label names the channel. Reason: in the brownfield run the agent's stage, verify and release entries and the human's approvals carried the same identity, so the log did not show who did what.
24. **`lean request` reminds the agent of the Session notes.** *(Decided 2026-11-08, after the live runs.)* For every kind except CRs, `lean request` prints "Reminder: the Session notes in aidlc-docs/<intent>/aidlc-state.md are still the template: update the Session notes before you stop (Status, Next)." while the Session notes (from `## Session notes` on, outside the generated region) still match the rendered template, whatever date it was rendered on. *(v0.3, 2026-11-09: for an intent made with `lean new --ideation`, also while they are still the template with the Ideation Status and Next that `new` wrote.)* Reason: in the multi-team, multi-day and brownfield runs the Session notes stayed the template through Inception.
25. **pstack-interrogate writes its brief to a file.** *(Decided 2026-11-08, after the live runs.)* The lead writes one brief for both reviewers to `aidlc-docs/<intent>/construction/build-and-test/review-brief.md` (the reviewer-prompt template filled in: the intent, the full diff with the acceptance-criteria table and any test output the reviewers need, the rubric with the AI-DLC Lean lens, the code-quality guide), does not change it after the dispatch, and commits it with review.md. It then dispatches `lean-reviewer-opus` and `lean-reviewer-k3` in one message, each with the same short prompt that names the file. pstack-swarm does the same with `aidlc-docs/<intent>/construction/swarm/brief.md` and one short prompt per worker (the path plus its slice). The reviewer and worker cards say to read a named brief file first. Models and read-only tools are unchanged. The same change adds an "Out-of-design changes" section to review.md, where the lead lists changes to interfaces, fields or behaviour that the design pages do not describe. Reason: in the brownfield run each prompt carried the 37 KB brief; Kiro starts a subagent only after its call is written out in full, so the K3 reviewer started 69 s late and the two overlapped for only 44 s. The live run also missed an undesigned `can_review` field.
26. **Contracts are gated like code.** *(Decided 2026-11-09, after the QA review of v0.3.)* A contract file (under `contracts_dir`, except `OWNERS` and the change requests in `changes/`) already counted as code for the fingerprint, the commit gate and `lean release`; the code-write gate now treats it as code too, in every mode. In multi-team mode the ownership check comes first: another team's contract needs that team's approved, open CR (§8.11); the team's own contracts and the CR-unlocked ones skip only that check. Then the usual gates apply: IDEATION when Ideation is used, requirements and design approved (or design skipped as small), released intents as in §8.8, and in regulated mode an active intent and the PLAN of the unit whose Paths hold the contract (every plan when no unit lists it). So unit-of-work.md lists each contract path in its owning unit's Paths, and a contract drafted before the approvals goes into application-design.md. Before, a team's own contract (and in single-team mode any contract, as a path under `aidlc-docs/`) skipped every approval gate, the regulated "no intent, no code" rule included. Reason: the QA review found that a contract skipped the new IDEATION gate while the fingerprint and the commit gate counted it as code. *(Third QA round, 2026-11-09: contracts_dir is normalised when lean.json is read. `./`, `//` and leading or trailing `/` are dropped, an absolute path inside the project is made relative, symlinks are resolved, and on a case-insensitive file system the letter case on disk is used, for the paths of tool calls too. A value with `..`, or one that leads outside the project, is refused and the default `aidlc-docs/contracts` is used. doctor fails on a value it had to rewrite or refused. OWNERS globs and CR paths written with the folder as lean.json names it still match. Reason: `"./aidlc-docs/contracts"` switched the ownership check, the OWNERS protection, the approval gates and the commit gate off for contracts.)* *(Fourth QA round, 2026-11-09, replacing part of the above: the configured path is kept as written and normalised only lexically; `..` is allowed again, as in v0.2, so a monorepo project can name a shared folder next to it (`../../shared-contracts`). A path is a contract when it is under the configured folder or under its resolved target (a symlink's), the configured name is the reserved folder under aidlc-docs/, and commands are checked against OWNERS by both names. doctor names only ambiguous values: empty, `.`, or an absolute path to no folder (read inside the project). Reason: refusing `..` left a shared contracts folder without any gate, and a symlinked folder let shell commands rewrite OWNERS and was listed as an intent.)*

## 9. v0.3: optional Ideation and Deployment/Operations (decided with the user on 2026-11-08)

Why: the user plans to give Lean to product managers later, so Ideation comes back as an optional phase. Deployment and operations come back too, also optional, so that the whole AI-DLC lifecycle is still recognisable. The agent only WRITES documents and config for deployment and operations; it never executes a deployment. Deployment stays with the team's CI/CD (e.g. GitLab → Argo), and the deny list stays as it is (see the last rule in §9.2). `VERSION` becomes 0.3.0.

### 9.1 New stages (one page each; file named after AI-DLC main's primary artifact for that stage)

| Phase | id | name | file (under `aidlc-docs/<intent>/`) | rule |
|---|---|---|---|---|
| Ideation | intent-capture | Intent Capture | ideation/intent-capture/intent-statement.md (incl. stakeholder map) | required when Ideation is used |
| Ideation | market-research | Market Research | ideation/market-research/market-research.md (competition, trends, build vs buy) | optional |
| Ideation | feasibility | Feasibility | ideation/feasibility/feasibility-assessment.md (constraints, RAID) | optional |
| Ideation | scope-definition | Scope Definition | ideation/scope-definition/scope-document.md (in/out, intent backlog) | required when Ideation is used |
| Ideation | team-formation | Team Formation | ideation/team-formation/team-assessment.md (roles, skills, teams) | optional |
| Ideation | rough-mockups | Rough Mockups | ideation/rough-mockups/wireframes.md (wireframes / user flow, text or links) | optional |
| Ideation | approval-handoff | Approval Handoff | ideation/approval-handoff/initiative-brief.md (brief + decision log) | required when Ideation is used; approval **IDEATION** |
| Construction | ci-pipeline | CI Pipeline | construction/ci-pipeline/ci-config.md (CI stages, quality gates) | optional; after build-and-test |
| Operations | deployment-pipeline | Deployment Pipeline | operations/deployment-pipeline/deployment-strategy.md (CD config, strategy, rollback runbook) | optional |
| Operations | environment-provisioning | Environment Provisioning | operations/environment-provisioning/environment-inventory.md | optional |
| Operations | deployment-execution | Deployment Execution | operations/deployment-execution/deployment-log.md (when, version, env, smoke tests, health) | optional |
| Operations | observability-setup | Observability Setup | operations/observability-setup/observability.md (logs, metrics, dashboards, alarms, SLOs) | optional |
| Operations | incident-response | Incident Response | operations/incident-response/runbooks.md (runbooks, escalation) | optional |
| Operations | performance-validation | Performance Validation | operations/performance-validation/load-test-plan.md (plan + results vs NFR targets) | optional |
| Operations | feedback-optimization | Feedback Optimization | operations/feedback-optimization/feedback-loop.md (SLO results, cost, follow-up intents) | optional |

Checked against AI-DLC main `d12d620` (`core/aidlc-common/stages/`): the 15 ids are main's. The names are short forms and not always main's: main's `name:` is Intent Capture & Framing, Feasibility & Constraints, Approval & Handoff and Feedback & Optimization for four of them (the code keeps Lean's names). Two file names are Lean's own, because main splits that stage into several files: market-research.md (main: competitive-analysis.md, market-trends.md, build-vs-buy.md) and observability.md (main: dashboards.md, alarms.md, slo-config.md, log-queries.md, tracing-config.md, anomaly-config.md). Main's folder is `operation/`; Lean keeps `operations/`, where release.md already lives. The order is main's, including incident-response (4.5) before performance-validation (4.6).

Order in the Stage progress list:
- Ideation (7 stages);
- Inception (5);
- Construction: per unit 4, then build-and-test, then ci-pipeline;
- Release (a phase of its own);
- Operations (7).

*(Corrected 2026-11-09.)* A unit named `ci-pipeline` (possible in v0.2) stays a unit, as in v0.2. Its pages live in subfolders (`construction/ci-pipeline/functional-design/functional-design.md`, …) and its plan in `construction/plans/`, so they do not collide with the CI Pipeline page `construction/ci-pipeline/ci-config.md`; `--unit ci-pipeline` works, and in regulated mode the PLAN gate covers the unit's paths as in v0.2. Only `plans` and `build-and-test` cannot be unit names.

### 9.2 Rules

- **Ideation is opt-in per intent.**
  - `lean new <slug> --ideation` starts with intent-capture (`lean new --ideation <slug>` works too).
  - Without `--ideation`, `lean new` records the whole Ideation phase as skipped, with the reason "not requested (lean new without --ideation)". This keeps developers' flow as before.
  - Until the INCEPTION/REQUIREMENTS approval is recorded, `lean stage start <ideation stage>` may still re-open Ideation; the start event supersedes that phase-level skip.
- **Ideation in use.** Ideation counts as used when any of its stages has a start or done record that is newer than its last phase skip. While it is used:
  - intent-capture, scope-definition and approval-handoff cannot be skipped. *(Fixed 2026-11-09.)* A skip of one of them recorded while Ideation was not in use no longer counts once it is: the stage is required again (its Stage progress row says "required now that Ideation is in use (its skip from before no longer counts)"), and the `stage start` or `stage done` that re-opens Ideation says so;
  - *(Fixed 2026-11-09.)* `request IDEATION` and the `approve IDEATION` line need all three recorded done with `lean stage done`; their pages alone are not enough (a refused approval line is logged with check `target`). *(Second QA round, 2026-11-09.)* So a required stage started again after `request IDEATION` (its page kept, so the request still covers the pages) holds the request back until its next `stage done`: Stage progress offers no approval line (the Approval Handoff row says `done · <date>; IDEATION also needs <stage> done`, or `in progress` when Approval Handoff itself was started again), Next says "Ideation: finish <stage> …", the prompt hook refuses the line (check `target`), and after the `stage done` the line is offered again and recorded. Likewise, an Approval Handoff started again to revise a rejected or stale IDEATION must be recorded done before the request: Next says to record the initiative brief done again, and `request IDEATION` refuses until then;
  - `approval-handoff` requests `approve IDEATION <hash>`. The hash is the sha256 over the existing ideation files (`\0`-joined, in stage order), with per-file shas stored like INCEPTION;
  - REQUIREMENTS/INCEPTION approvals, code writes and release all need IDEATION approved. Stale handling is the same as for other approvals: in standard mode a stale IDEATION (a page changed since) still lets the requirements be approved and code be written, shown as stale; regulated mode needs it current; release needs it current in every mode (`lean release`, `request RELEASE` and the RELEASE approval line, which is refused when IDEATION or the requirements are stale or rejected);
  - `approvers` may restrict IDEATION, e.g. to product managers.
- **Operations are optional in every mode.**
  - They may be recorded before or after the RELEASE approval.
  - After RELEASE, only Operations stages (and ci-pipeline) accept stage commands; every other stage is refused as before.
  - *(Corrected 2026-11-09.)* The RELEASE hash covers release.md only. release.md holds the commit, the code fingerprint, the verify result, a Stages section (the Stage progress lines when `lean release` ran, so each Operations stage's state then: done, skipped or not started), the Approvals table and Open items; the Operations pages' contents are not hashed. Editing or adding an Operations page after the approval does not void it: those pages are records. Product config (CI files, manifests, IaC) is in the code fingerprint, so a change after `lean release` needs `lean verify` and `lean release` again before RELEASE. Nothing new is gated on the Operations pages.
  - Post-release product-file changes (e.g. alert rules as code) follow the existing released-intent rule: allowed in standard mode, a new intent in regulated mode.
- **Phase skip.**
  - `lean stage skip ideation --reason "..."` and `lean stage skip operations --reason "..."` skip every stage of that phase that has no record yet (done or skipped), decided from the records (a done Approval Handoff, shown `[-]` until IDEATION is requested, is not skipped). `operations` does not include ci-pipeline; skip that one on its own.
  - *(Implemented 2026-11-08.)* Once IDEATION has been requested for an intent with Ideation in use (pending, approved or rejected), `stage skip ideation` is refused: the human decides it. After RELEASE it is refused too.
  - In Stage progress, a phase whose stages are all skipped by one phase skip is shown as ONE line: `- [S] Ideation — skipped: <reason>` or `- [S] Operations — skipped: <reason>`.
- **Next.**
  - A new intent without --ideation: unchanged.
  - With Ideation in use: the next ideation stage, then IDEATION approval, then Inception. *(2026-11-09.)* Once IDEATION has been requested (pending, approved or rejected), Next no longer points to an optional Ideation stage that was never started: its new page would void the request or the approval. One already started is still to be finished. *(Second QA round.)* This holds after the approval too: the Next before the release lists a started optional Ideation stage among the stages with no record yet, and leaves out only those never started (before, it left out every optional Ideation stage once IDEATION was requested). A stale IDEATION: request it again; a rejected one: revise the pages as the human asked, then request again (with Approval Handoff recorded done again if it was started again, see above).
  - After RELEASE, while Operations stages have no record: "optional: record deployment and operations (skill aidlc-lean-operations) or `lean stage skip operations --reason ...`". It is guidance only, and the intent stays RELEASED.
- **The deny list is unchanged.** *(Corrected 2026-11-09.)* It is a short default list (`terraform apply`, `kubectl apply` and a few more), not a deployment control: it does not catch every deploy command, and teams extend it with `deny_commands` in aidlc-docs/lean.json (which replaces the default list, so keep its entries). "Never deploy" is an instruction to the agent in the steering and the operations skill, not something the tool enforces. The real control is the team's pipeline and permissions (e.g. the agent's credentials cannot deploy), in line with "guardrail, not a security boundary".

### 9.3 Content

- 15 new one-page templates.
- *(Added 2026-11-09.)* install.sh no longer replaces `.kiro/aidlc-lean/` as a whole. It replaces the kit's own files there, records the sha256 of each template it installs in `.kiro/aidlc-lean/kit-templates.sha256` (for an install without that file it knows the v0.2.0 templates), and on a re-install replaces only a template that still has a sha256 the kit installed. A template a person changed is kept, with the kit's version next to it as `<name>.kit-new`; one the kit does not ship is kept as the team's; both are printed as "Kept …". The kit's own old templates (the v0.1 names in a v0.1 install, or ones the kit dropped and nobody changed) are removed, and only those are dropped from the git index. Reason: QA found that a re-install silently overwrote changed templates, deleted added ones and reported them as old kit names. *(Second QA round, 2026-11-09.)*
  - A kit version is offered as `<name>.kit-new` only once: the manifest also records each offered version as `<sha256>  <name>.kit-new`. Once the person has merged and deleted the copy, a re-install of the same kit says nothing; a newer kit version of that template is offered again. While the copy is still there, a re-install writes it again.
  - A manifest that is not UTF-8, or has lines that are neither `<sha256>  <name>` records nor comments, gets one `note:`; its records are still read, and it is written again without those lines.
  - *(Third QA round, 2026-11-09.)* install.sh first runs a read-only check, before `git init` and before it creates any folder: it reads every template and the manifest, decides everything, checks that every file it will write can be written (the kit's script and templates, the manifest, hooks, steering, the skill folders it replaces, the pstack pack, and for `lean init` `aidlc-docs/audit/`, `.aidlc-lean/`, `.gitignore` while it lacks `.aidlc-lean/`, and in multi-team mode the contracts folder and its `changes/`) and that aidlc-docs/lean.json is valid JSON. For a file or folder that does not exist yet it checks the nearest existing folder; a refusal names the file or folder that stops it. *(Fourth QA round: .gitignore and skill folders not there yet were missed.)* A problem stops the install with "…; nothing was changed.", and nothing is. Then it changes things, deciding the same way. A failure after the check (a full disk, `lean init` failing) ends with "install.sh: stopped part way …": some kit files may already be the new ones, and re-running after the fix is safe.
  - A v0.1 install is recognised by its v0.1-only names: no manifest, at least one v0.1 template name in exact case (`SPEC.md`, `PLAN.md`, `STATE.md`, `REVIEW.md`, `UNITS.md`, `DECISIONS.md`, `RELEASE.md`, `AUDIT-PACK.md`, `CR.md`), and no later name apart from `lean.json` (v0.1 shipped it too). There its v0.1 templates are removed and its `lean.json` template is replaced. In any later install a file with a v0.1 name is the team's.
  - Case-only collisions: on a case-insensitive file system a team's `CR.md` is the same file as the kit's `cr.md`. It is kept, never written through, and the kit's version goes to `cr.md.kit-new`, offered once like any other (likewise for any name that differs from a kit template only in case).
  - Reason: a real v0.1 install was never recognised (`lean.json` is a current name too), so its templates were kept as the team's and git kept the old `CR.md` and `DECISIONS.md`; a hand-merged template got its `.kit-new` back on every re-install; a non-UTF-8 manifest stopped the install halfway, after the hooks, steering and skills were replaced.
- New skills, each ≤ 600 words: `aidlc-lean-ideation`, written for product managers (how to run each stage, one page each, the IDEATION hand-off), and `aidlc-lean-operations` (CI, deployment, environments, observability, performance, runbooks, feedback; write, don't execute; record the real deployment after it happens).
- Existing skills and the steering mention the optional phases. The steering stays ≤ 1,000 words.
- README and COMPARISON drop "没有构想、部署、运维阶段".
