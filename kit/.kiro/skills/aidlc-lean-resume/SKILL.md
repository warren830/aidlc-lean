---
name: aidlc-lean-resume
description: Use for multi-day or multi-session AI-DLC Lean work - keeping the Session notes in aidlc-state.md current, checkpoints, resuming in a new chat, and handing over to someone else.
---
# Multi-day work: checkpoint and resume

Chats end and context fills up; files persist. Anything not written to a file is lost to the next session.

## aidlc-state.md has two owners
- **The progress region**, between the `lean:begin progress` and `lean:end progress` markers: Stage progress and the Stage log (what each stage did, from the `--note` of `lean stage done`, with output hashes, who and when). The tool regenerates it from the ledger, approvals and verify results included. Never edit inside the markers; edits are overwritten. To change what it says, run the stage command (`lean stage done`, `lean stage skip`); `lean status` brings it up to date, e.g. after a pull.
- **Session notes**, below the markers: yours, and the hand-over. Keep it under a page:
  - `Status:` one line, e.g. `Construction: code generation for api, step 3 of 5`.
  - **Next**: ordered and concrete; the first item is what the next session does first.
  - **Open questions and blockers**: each with who should answer.
  - **Notes for the next session**: traps, half-done work, commands that matter.
  - Multi-team: each team keeps its own `### Next (team <name>)` subsection, with its Status and blockers, and edits only that one (skill `aidlc-lean-multi-team`).

## When to update the Session notes
- After each stage and each plan step.
- Before waiting on a human or another team.
- When the chat feels long (Kiro shows how full the context is; update at about 70%).
- At the end of every session.
- When a hook reminds you.

Commit aidlc-state.md with the work, so teammates and other machines see it.

## Resuming
At session start the hook adds a status block (`[AI-DLC Lean] session context`) with the first Next items and the Stage progress lines. It is capped at 40 lines; if it ends with `(truncated; …)`, run `lean status` for the rest. After a long break in the same chat (4 hours by default), the next human message gets a fresh block; the chat still holds its old context. Then:
1. Run `lean status`.
2. Read aidlc-state.md (Session notes, then the Stage log), decisions.md, and the pages the first Next item needs (e.g. the unit's code-generation plan).
3. Pull if teammates may have pushed; run `git log --oneline -15` and `git status`.
4. Continue with the first Next item. If anything is unclear or stale, ask before acting.

## Starting a fresh chat on purpose
At a stage or step boundary:
1. Update the Session notes and commit.
2. Tell the human: "Good point to continue in a new chat: `/chat new`, then say `continue intent <id>`."

## Going back to an older chat
Plain `kiro-cli chat --resume` reopens the newest chat in this folder. To return to an older one, the human runs `kiro-cli chat --resume-id <session id>` (`kiro-cli chat --list-sessions` shows the ids). A resumed chat is not a fresh context: it remembers writing the code, so it cannot review that code.

## Handing over to another person or team
Write the hand-over in the Session notes (Next, Open questions and blockers, Notes); commit and push everything. A product manager hands Ideation over this way after the IDEATION approval. The receiving person runs `lean use <intent>` in their clone. Approvals, stage records and verify results come with the ledger in `aidlc-docs/audit/`. Verify reruns on their machine: its results are tied to the exact code.
