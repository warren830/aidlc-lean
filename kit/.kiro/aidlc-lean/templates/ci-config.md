# CI Config: {{TITLE}}

AI-DLC stage: Construction · CI Pipeline · Intent: {{INTENT}}
<!-- Optional, after Build and Test. Run it when CI is new or changes; skip it when the existing CI is adequate. One page that describes the pipeline. The pipeline file itself (e.g. .gitlab-ci.yml, a GitHub Actions workflow, buildspec.yml) is product code: it lives in the repo, and lean verify runs again after it changes. No secrets: name the CI variable or vault entry instead. -->

## CI Tool and Branch Strategy
<!-- The CI system, the pipeline file's path, which branches and merge requests run it, and what must pass before a merge. -->

## Pipeline Stages
| Stage | Runs (commands) | Trigger | Fails the pipeline when |
|---|---|---|---|
| build |  |  |  |
| test |  |  |  |

## Quality Gates
<!-- Every command in "checks" of aidlc-docs/lean.json (what lean verify runs) is enforced here too, so CI and verify agree. Add coverage, lint, security and dependency scans, and contract tests, as the team requires. -->
| Gate | Command / tool | Threshold | A lean verify check? |
|---|---|---|---|
|  |  |  | yes / no |

## Artifacts
<!-- What the pipeline produces (image, package, bundle), where it is stored (registry, artifact repository, bucket), how it is versioned (e.g. by commit sha), and how the deployment pipeline picks it up. -->
