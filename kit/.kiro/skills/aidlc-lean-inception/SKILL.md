---
name: aidlc-lean-inception
description: Use for the Inception phase of an AI-DLC Lean intent - clarifying questions, reverse engineering, requirements, user stories, application design, units of work, and the INCEPTION approval.
---
# Inception: what to build and why

Each stage: `lean stage start <id>`, fill its page, `lean stage done <id> --note "<inputs, outputs, decisions>"`; or `lean stage skip <id> --reason "<why>"`. Workspace Detection and Workflow Planning are folded in: read the repo first. After Ideation, start from the approved initiative brief and its pages; ask only what they leave open. Before every stop (the question batch, an approval request), update aidlc-state.md's Session notes: Status, Next, Open questions.

## Clarifying questions (once, at the start)
- First read the code, docs and contracts the change touches; never ask what they answer.
- Ask the rest in ONE numbered batch, each with your recommended answer, so the human can answer "all as recommended" or correct some.
- Ask about behaviour and edge cases: who may do what, limits, money and rounding, time zones, state transitions, failures. Decide implementation choices yourself; log them in decisions.md.

## 1. Reverse Engineering (`reverse-engineering`)
Brownfield only. `architecture.md`: system overview (what exists; how it is built, run, tested), the touched components with paths, data, integration points, risks; read the code, do not guess. Skip for greenfield, or when an earlier intent's architecture.md is still current (name it).

## 2. Requirements Analysis (`requirements`, never skipped)
- **Size**: `large` for a new public module, API or data model, a schema or API change, several modules, a migration, or a risky change; else `small`. Only small may skip application design.
- **Goal** (2-4 sentences); **Not doing**.
- **Acceptance criteria** AC-1…: testable, with concrete values (input → expected output, status code or state), including the unhappy paths: who gets 401/403, validation, limits.
- **Non-functional targets**: numbers, not adjectives ("p95 < 300 ms at 50 rps"), and the applicable security, privacy and compliance rules.
- **Assumptions** A-1…: what you guessed, for the human to confirm.
- **Questions and answers**: the batch, with only the answers the human gave (what they left to you is an assumption). A question stays open only if the human says it does not block.
- **Contracts touched**: multi-team only.

## 3. User Stories (`user-stories`)
Run for several user types or changed user-facing flows. Personas inline, one line each; then US-1… ("as a … I want … so that …"), each linked to the ACs that prove it (add missing ACs). Skip for internal or single-persona work and simple fixes.

## 4. Application Design (`application-design`)
Components and responsibilities; interfaces and methods (signature, input → output, errors, who may call); dependencies with a small diagram; data model and migrations; key decisions. High level: business rules belong to Functional Design.

## 5. Units Generation (`units`)
Run when the work splits across teams, services or deployables. `unit-of-work.md` is one table; its first column, `Unit`, holds short lowercase names (`api`, `web`), the folder names and `--unit` values. Units meet only at contracts (skill `aidlc-lean-multi-team`). Skip for one unit, called `app`.

## Approval
When the Inception pages are done, run `lean request INCEPTION` (requirements.md and application-design.md together) and show the human its exact line. If they want requirements settled first: `lean request REQUIREMENTS` now, `lean request DESIGN` after the design.

Record a stage marked `(edited since)` again (`lean stage done`, noting what changed) before the request. With Ideation, IDEATION must be approved first (and current in regulated mode). Write no code before the approval. On a rejection or correction, update the page and request again: every edit voids the old approval.
