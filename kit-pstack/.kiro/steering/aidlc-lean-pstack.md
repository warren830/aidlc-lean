---
inclusion: always
---
# AI-DLC Lean quality pack (adapted from pstack)

Load these on-demand skills at the matching AI-DLC stage.

- **Existing code, big change**: `pstack-swarm` for a read-only survey (one worker per module) during reverse engineering. Before you change existing behaviour, use `pstack-blast-radius`.
- **Data and design**: `pstack-principle-model-the-domain` before you choose data shapes.
- **Code generation**:
  - `pstack-principle-sequence-verifiable-units` for the code-generation plan's steps;
  - `pstack-principle-boundary-discipline` for validation and authorization;
  - `pstack-principle-test-behavior-not-implementation` when writing tests;
  - `pstack-principle-fix-root-causes` when debugging.
- **Before calling anything done**: `pstack-principle-prove-it-works`, then `lean verify`.
- **Review**: `pstack-interrogate`, with `lean-reviewer-opus` and `lean-reviewer-k3` in parallel; the verdict goes to `aidlc-docs/<intent>/construction/build-and-test/review.md`.
- **The human corrects the same mistake twice**: `pstack-correct`.

Subagents:
- `lean-worker` (the session's model);
- `lean-reviewer-opus`, `lean-reviewer-k3` (read-only, no shell: put the diff in their brief).

At most 5 at once. AI-DLC Lean's gates apply to them as to you.
