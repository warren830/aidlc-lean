---
name: aidlc-lean-ideation
description: Use for the optional Ideation phase of an AI-DLC Lean intent - product discovery for product managers, the 7 stages and the IDEATION hand-off approval.
---
# Ideation: from an idea to an approved brief

Ideation is the optional product phase before requirements. The product manager (PM) answers, reads each page and types the approval; the agent asks, drafts and runs `lean`. One plain-language page per stage, in `ideation/<stage>/`.

## Start or skip
- Start: `lean new <slug> --title "<title>" --ideation`. Intent Capture comes first.
- Without `--ideation`, the phase is recorded as skipped; until requirements are approved, `lean stage start intent-capture` brings it back.
- To drop it: `lean stage skip ideation --reason "<why>"` skips every unrecorded stage; refused once IDEATION was requested, approved or rejected.

## The 7 stages
Each: `lean stage start <id>`, fill it with the PM, `lean stage done <id> --note "<used, produced, decided>"`. Skip an optional stage that adds nothing (`lean stage skip <id> --reason "<why>"`).

| Stage (id) | Page | Run it |
|---|---|---|
| Intent Capture (`intent-capture`) | intent-statement.md: problem, customer, success metrics, why now, stakeholders | always |
| Market Research (`market-research`) | market-research.md: alternatives, trends, build-or-buy | it competes, or could be bought |
| Feasibility (`feasibility`) | feasibility-assessment.md: viability, constraints, RAID log | integrations, regulation, technical doubt |
| Scope Definition (`scope-definition`) | scope-document.md: in, out, prioritised backlog | always |
| Team Formation (`team-formation`) | team-assessment.md: people, capacity, skill gaps, RACI | the team is unsettled |
| Rough Mockups (`rough-mockups`) | wireframes.md: user flow, screens as text or links | users see something new |
| Approval Handoff (`approval-handoff`) | initiative-brief.md: summary, go/no-go, decision log | always |

Once Ideation is used, the "always" stages cannot be skipped; an earlier skip no longer counts.

## How to run it
- **One question batch** at Intent Capture: numbered, each with a recommended answer and a "not known yet" choice. Later, only what blocks you.
- **Never invent** customers, metrics, competitors, prices, stakeholders or dates: they come from the PM or a named source. A guess is an assumption (A-1…) for the PM to confirm; an unknown, an open question naming who answers.
- **Short pages**: tables and lists; the brief summarises the others, never copies them.
- Log decisions in the brief's decision log (build-shaping ones also in decisions.md). Before every stop, update aidlc-state.md's Session notes.

## The IDEATION approval
1. Once all three "always" stages have their `stage done` (pages alone do not count), `lean request IDEATION`. It prints a line like `approve IDEATION 1a2b3c4d`, bound to these pages. Restarting one of them, even to revise the brief, holds the request back until its next `stage done`.
2. Show the PM that line. They (or whoever lean.json's `approvers` names) read the brief and, if they agree, type it themselves; never approve for them. Otherwise they type `reject IDEATION <reason>`: revise, then request again.
3. After the request, Next offers only the optional stages already started (finish them): a new, edited or removed page voids the request or the approval; request again (release, and regulated mode, need it current).

Until IDEATION is approved, requirements cannot be approved: no code, no release.

## Hand-off to development
Inception (skill `aidlc-lean-inception`) starts from the brief:
- requirements.md: Goal from the problem and success metrics, Not doing from Out of Scope, ACs from Must items, NFR targets from constraints;
- developers ask only what Ideation left open;
- stories use the stakeholders and wireframes, units the team plan;
- other backlog items become later intents (`lean new`).
