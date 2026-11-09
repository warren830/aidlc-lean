---
name: aidlc-lean-operations
description: Use for the optional CI Pipeline and Operations stages of an AI-DLC Lean intent - CI, deployment and rollback, environments, observability, load tests, runbooks, feedback. Write documents and config; never deploy.
---
# CI and Operations: write it down, let the pipeline deploy

## The rule
You write documents and config; you never execute a deployment. The team's CI/CD (e.g. GitLab, then Argo CD) provisions, deploys and rolls back. The rule covers every deploy, provisioning or load-test run against a shared environment, blocked by a hook or not. Where a person must act, write the exact steps for them.

Product config (CI files, manifests, Helm values, IaC, alarms or dashboards as code) is code: the code-write gate applies, and `lean verify` must pass again after it changes. Pages under `aidlc-docs/` are records. No secrets anywhere: name their source.

## The stages (optional, one page each)
Each: `lean stage start <id>`, fill the page, `lean stage done <id> --note "<inputs, outputs, decisions>"`; or `lean stage skip <id> --reason "<why>"`. Describe the real pipeline and environments: read the repo, ask the rest, never invent.

| Stage (id) | Page | Run when |
|---|---|---|
| CI Pipeline (`ci-pipeline`; Construction, after verify) | `construction/ci-pipeline/ci-config.md`: stages, quality gates (incl. the verify `checks`), artifacts | CI is new or changes |
| Deployment Pipeline (`deployment-pipeline`) | `deployment-strategy.md`: CD config, strategy, promotion, flags, rollback | shipping is new or changes |
| Environment Provisioning (`environment-provisioning`) | `environment-inventory.md`: environments, network, secrets by name, validation | environments change |
| Deployment Execution (`deployment-execution`) | `deployment-log.md`: version / commit, environment, time, smoke tests, health, result | after a real deployment |
| Observability Setup (`observability-setup`) | `observability.md`: logs, metrics, dashboards, alarms, SLOs | monitoring changes |
| Incident Response (`incident-response`) | `runbooks.md`: runbooks per alarm, escalation | on-call needs steps |
| Performance Validation (`performance-validation`) | `load-test-plan.md`: a scenario per NFR target, then results | targets need load proof |
| Feedback Optimization (`feedback-optimization`) | `feedback-loop.md`: SLO results, cost, follow-up intents | weeks after go-live |

Operations pages live in `operations/<stage>/`.

## Before RELEASE: prepare
- The pages that plan it: ci-pipeline, deployment-pipeline (always with a rollback), environment-provisioning, observability-setup, incident-response, and the plan part of performance-validation.
- Their config files: commit them and run `lean verify` before `lean release`, so the review and release record cover them. A product file changed after `lean release` means `lean verify` and `lean release` again.
- Finish them before `lean release`, which lists each stage's state in release.md. RELEASE covers only release.md, not the pages: later page edits are records.

## After deployment: record
Operations stages and ci-pipeline still take stage commands after RELEASE; the intent stays released.
- **deployment-execution**: once the team's pipeline deployed (staging may come before RELEASE), fill deployment-log.md from the pipeline run and whoever watched it. Never record a deployment that has not happened.
- **performance-validation**: add the team's results, target against actual, and run `lean stage done` again.
- **feedback-optimization**: after some weeks in production. Each follow-up becomes a new intent (`lean new <slug>`, `--ideation` if it needs product discovery).

A product file changed after RELEASE (e.g. an alarm threshold) follows the released-intent rule: a small edit in standard mode; otherwise, and always in regulated mode, a new intent.

## Skipping
- The whole phase: `lean stage skip operations --reason "<why>"` (e.g. "the platform team deploys and monitors") skips every Operations stage with no record yet.
- ci-pipeline is not part of it: `lean stage skip ci-pipeline --reason "existing CI is adequate"`.

After RELEASE, `lean status` suggests them until each has a record.
