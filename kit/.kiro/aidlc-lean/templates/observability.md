# Observability: {{TITLE}}

AI-DLC stage: Operations · Observability Setup · Intent: {{INTENT}}
<!-- Optional. Run it when logs, metrics, dashboards, alarms or tracing are new or change. One page, starting from the targets in requirements.md and nfr-design.md. Dashboards, alarm rules and queries kept as code are product files: write them in the repo; the team's pipeline applies them. -->

## Logs
<!-- What is logged (structured fields, a correlation or trace id), where logs go, retention, saved queries for the common questions, and what is never logged (secrets, personal data). -->

## Metrics
<!-- The golden signals per service: latency (p50 / p95 / p99), traffic, errors, saturation; plus the business metrics from the intent statement or requirements. Name each metric as the code emits it. -->
| Metric | Source | Unit | Why |
|---|---|---|---|
|  |  |  |  |

## Tracing
<!-- Which calls are traced, the sampling rate, how the trace id crosses services. Write "none" if none. -->

## Dashboards
| Dashboard | Audience | Panels | Link / file |
|---|---|---|---|
|  |  |  |  |

## Alarms
<!-- Condition and threshold, severity, who is notified and how, and the runbook in runbooks.md that answers it. No alarm without a runbook. -->
| Alarm | Condition | Severity | Notifies | Runbook |
|---|---|---|---|---|
|  |  |  |  |  |

## SLOs
<!-- From the NFR targets: the SLI (what is measured), the objective, the window, and the error budget policy (what happens when it burns fast). -->
| SLO | SLI | Objective | Window | Error budget policy |
|---|---|---|---|---|
|  |  |  |  |  |
