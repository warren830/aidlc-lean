---
name: pstack-interrogate
description: Multi-model adversarial review of a change. Use at the AI-DLC Lean review step, or for "interrogate", "adversarial review", "multi-model review", "stress test this". Two reviewers on different models challenge the change and you write a synthesized verdict to the intent's review.md.
---

# Interrogate: multi-model review

Dispatch one reviewer per model to review a change adversarially. The adversarial signal comes from model diversity, not assigned personas. The deliverable is a synthesized verdict in `aidlc-docs/<intent>/construction/build-and-test/review.md`. Do NOT auto-apply changes while reviewing.

## Step 1, Scope

- The diff: `git diff <base>..HEAD`, where base is the commit before the intent's work (find it with `git log`), or the files the human names.
- The intent's pages under `aidlc-docs/<intent>/`: `inception/requirements/requirements.md` (goal, AC-n, NFR targets), `inception/application-design/application-design.md` if it exists, and per unit the design pages under `construction/<unit>/` (BR-n) and `construction/plans/<unit>-code-generation-plan.md` (the test for each AC and BR).

## Step 2, Intent

State the intent in one paragraph from the requirements goal, the acceptance criteria and the commit messages. If you are unsure about the intent, ask the human before proceeding.

## Step 3, Write the brief once

Write one brief for both reviewers to `aidlc-docs/<intent>/construction/build-and-test/review-brief.md`: the template in `references/reviewer-prompt.md` with its placeholders filled in.
- `{INTENT}`: the intent paragraph.
- `{DIFF_OR_FILES}`: the full diff plus the acceptance criteria table from requirements.md. The reviewers have read tools only (no shell, no writes), so they cannot run git or tests: put any test output they need in the brief.
- `{RUBRIC_CONTENTS}`: the contents of `references/rubric.md`, followed by the AI-DLC Lean lens below.
- `{CODE_QUALITY_CONTENTS}`: the contents of `references/code-quality-review.md`.

The AI-DLC Lean lens:
- Every AC and BR has the test its code-generation plan maps it to, and that test asserts the expected value.
- Authorization covers every new or changed endpoint, including admin and maintenance routes.
- Nothing outside the approved requirements and design changed without a decisions.md line.
- Contract changes match approved change requests.

The brief records what the reviewers were shown: do not change it after the dispatch, and commit it with review.md.

## Step 4, Dispatch the reviewers

In ONE message, call `invoke_sub_agent` twice:

- `lean-reviewer-opus`
- `lean-reviewer-k3`

Give both the same short prompt that names the brief, for example: "Adversarial review: read aidlc-docs/<intent>/construction/build-and-test/review-brief.md and follow it. Return your findings in your reply." Never paste the brief into the prompt. Kiro starts a subagent only after its call has been written out in full, so a long prompt starts the second reviewer late and spends the brief's tokens twice; with short prompts both start together.

Their models are fixed in `.kiro/agents/`. If one fails to start, for example because that model is not enabled on this Kiro install, say so and continue with the other.

Each reviewer returns its findings in its reply. It can read and search the repo for context, but it cannot change files or run commands.

## Step 5, Synthesize

As results come back, build one picture.
- Merge findings that describe the same issue differently, and note which models raised each.
- Findings that both models raised independently are the highest signal.
- Read a lone model's finding, but weight it accordingly.
- Note disagreements. If one model flags something and the other explicitly says the opposite, that is context for the verdict.
- When a reviewer names a command or test that would confirm a finding, run it yourself and use the result.

## Step 6, Lead judgment

You are the lead reviewer: a pragmatic senior engineer, not a neutral aggregator. Read `references/lead-judgment.md`. Put every finding in one bucket, with the model(s) that raised it and a one-line rationale:

- **Act on**: real issues affecting correctness, security or maintainability; they would block a real PR.
- **Consider**: legitimate, but not clearly worth fixing now.
- **Noted**: valid but not actionable now.
- **Dismissed**: wrong, nitpicky or missing context, with a brief reason.

## Output

Write `aidlc-docs/<intent>/construction/build-and-test/review.md` with these sections: Intent, Reviewers (agent, model, number of findings), Act on, Consider, Noted, Dismissed, Agreement map, Out-of-design changes. In the last one, check the diff against application-design.md and the design pages yourself: list each change to an interface, field or behaviour they do not describe, with its decisions.md line or "no decision recorded", or write "none".

Then, as a separate step, fix the Act-on items with tests, run `lean verify`, and add to review.md what was fixed.


---

*Adapted from pstack 0.15.32 (MIT License, (c) 2026 Lauren Tan, https://github.com/cursor/plugins/tree/main/pstack) for AI-DLC Lean on Kiro CLI. See `.kiro/aidlc-lean/LICENSE-pstack`.*
