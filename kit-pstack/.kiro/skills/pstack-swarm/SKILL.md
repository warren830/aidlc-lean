---
name: pstack-swarm
description: Fan out up to 5 parallel subagents, drain them, and return one report. Use in AI-DLC Lean for read-only surveys of existing code, multi-model checks and verification gauntlets; parallel code writing only for disjoint units.
---

# Swarm

Open a todo list with one entry per phase before launching anything: 1. Frame, 2. Fan out, 3. Aggregate, 4. Report.

## Phase A: Frame

1. State the done predicate and the artifact or report the swarm must return.
2. Choose the shape:
   - partition the work into slices (one module, acceptance example or risk area each);
   - race N workers on identical briefs, deciding up front between `first pass`, `rank all` and `best-of`;
   - or mix both.
3. Pick the workers:
   - `lean-worker` runs on the session's model and can write files and use the shell;
   - `lean-reviewer-opus` and `lean-reviewer-k3` give model diversity for judgment-heavy questions. They are read-only: read tools only, no shell.
4. At most 5 workers. Reviewers report only in their reply. A `lean-worker` may instead write its report to its own file, `aidlc-docs/<intent>/construction/swarm/<worker>.md`.

## Phase B: Fan out

Write the shared brief once to a file, `aidlc-docs/<intent>/construction/swarm/brief.md`: the goal, the scope, how to verify, what to report, and the material every worker needs. A reviewer cannot run commands, so put the diff and any command output it needs in the brief. Reports use `PASS`, `ISSUES` or `BLOCKED` with evidence (`file:line`, command output). A worker that can prove a defect lists every defect it can prove, not only the first.

Then dispatch all workers in ONE message with `invoke_sub_agent`, each with a short prompt: the brief's path plus that worker's own slice or race arm. Kiro starts a subagent only after its call has been written out in full, so long prompts start the workers one after another; short ones start them together. A worker sees nothing of this chat, so the brief and its prompt must stand alone.

**Writing code in parallel** is for `lean-worker` only, and only when all of these hold:
- `inception/application-design/unit-of-work.md` (if the intent has none, create it with `lean stage start units` and finish that stage first) or the code-generation plan gives each worker disjoint paths;
- requirements and application design are approved (or the design stage was skipped for `Size: small`), and, in regulated mode, the code-generation plan of every unit the workers touch;
- workers run no git commands.

After all workers finish, run `lean verify` once on the combined result. AI-DLC Lean's hooks gate every worker's writes exactly like your own.

If a worker drops out, proceed with N-1 and note it.

## Phase C: Aggregate

- Read the results. When a reviewer names a command that would confirm a finding, run it yourself.
- Drop a result that lacks the evidence its brief asked for and re-dispatch that worker once. After a second miss, record a gap; a gap does not count as a pass.
- For coverage, every slice needs a result. For a race, apply the rule declared up front.
- Do not paste raw worker output.

## Phase D: Report

Return one consolidated report: a result table, one line per issue, and any gaps or dropouts (plus the race rule, if used). Move lasting conclusions to where they belong: the assumptions in requirements.md, review.md, or the Session notes in aidlc-state.md.


---

*Adapted from pstack 0.15.32 (MIT License, (c) 2026 Lauren Tan, https://github.com/cursor/plugins/tree/main/pstack) for AI-DLC Lean on Kiro CLI. See `.kiro/aidlc-lean/LICENSE-pstack`.*
