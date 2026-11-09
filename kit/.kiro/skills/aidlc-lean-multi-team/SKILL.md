---
name: aidlc-lean-multi-team
description: Use in AI-DLC Lean multi-team mode - units of work and owner teams in unit-of-work.md, contracts first, change requests to other teams' contracts, team identity, and cross-team hand-offs.
---
# Several teams, one product

## Who is who
- Each clone has a team, set by a person (`lean init --team <name>` or `AIDLC_LEAN_TEAM`); you never change it. `lean status` shows it.
- `aidlc-docs/contracts/OWNERS` maps contract paths to teams. Format: `<glob> <team>`; the last match wins. You cannot edit it.
- Code ownership and merge approvals are the Git server's job (CODEOWNERS, merge-request approvals).
- Each intent has an owner team, the one that started it (`Owner team` in aidlc-state.md); it runs the review and the release (if a product manager started it, a person sets the releasing team there). Other teams build their units and push.

## Plan the split: unit-of-work.md
Run Units Generation (`lean stage start units`) for an intent that spans teams. `inception/application-design/unit-of-work.md` has one row per unit: `Unit` first (a short lowercase name, used as folder name and `--unit` value), then owner team, paths, depends on, contracts, stories/ACs, status.

Units meet only at contracts. Avoid two teams editing the same files. Each team builds its own units, one at a time, in "Depends on" order.

## Contracts first
- Contracts live under `aidlc-docs/contracts/<team>/`: OpenAPI, AsyncAPI, JSON Schema or protobuf, with examples. List the ones the intent reads or changes in requirements.md, "Contracts touched".
- Agree on the contract before both sides build: the consumer builds against it with a stub or mock; the provider proves it with contract tests in `checks`.
- Additive changes (new optional fields, endpoints) keep old consumers working; breaking changes need a new version and a migration window agreed with every consumer.
- Contract files count as code: they wait for the same approvals (IDEATION when used, requirements, design; regulated mode: the plan of the unit holding them) and need a passing `lean verify` before a commit. List each contract path in its owning unit's Paths column; until the approvals, draft it in application-design.md.

## Changing a contract another team owns
1. Run `lean cr new <slug> --owner <team> --paths <contract-file>`. This creates `aidlc-docs/contracts/changes/CR-<yourteam>-<n>-<slug>.md`.
2. Fill in the change, why, compatibility and affected consumers; commit and push.
3. Someone from the owning team, in their clone, runs `lean request CR-<yourteam>-<n>` and, if they agree, types the approval line.
4. Their approval reaches you through `aidlc-docs/audit/` when you pull. Until the CR is closed, only your team may edit the paths it lists, and only as it describes. Editing the CR voids its approval.
5. Once the change has shipped, either team closes the CR: `lean cr close CR-<team>-<n> --reason "<what shipped>"`. A closed CR unlocks nothing.

Your own team's contracts need no CR.

While a CR waits, build against the proposed contract behind a stub; note it in your blockers.

## Hand-offs between teams
- Put what the other team needs in the CR and the Session notes, not in chat. There each team keeps its own `### Next (team <name>)` subsection (Status, Next, blockers) and edits only its own; the session-start context shows yours first.
- `lean status` lists change requests waiting for your team: deal with them first.
- Merge order follows the "Depends on" column. Integration runs in `checks`, so a consumer's verify fails if the provider's contract test fails.
- A merge conflict in what the tool writes (aidlc-state.md's progress region, build-and-test-summary.md): run `lean verify`, which rewrites both, then commit. Merge the Session notes by hand. Ledger files are per clone and never conflict.
