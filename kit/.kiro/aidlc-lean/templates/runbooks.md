# Runbooks: {{TITLE}}

AI-DLC stage: Operations · Incident Response · Intent: {{INTENT}}
<!-- Optional. Run it when the service needs on-call steps. One page: one runbook per likely failure mode, each answering an alarm in observability.md. The steps are for the person on call; the agent writes them, it does not run them. -->

## Recovery Targets
<!-- RTO (how long it may be down) and RPO (how much data may be lost), from requirements.md; backups: what, how often, where, and the last restore test. -->
- RTO: 
- RPO: 
- Backups: 

## Runbooks
<!-- Per failure mode. Confirm: the dashboard or query that shows it. Mitigate: the steps; a rollback follows deployment-strategy.md. Automated remediation: what fixes itself, if anything. -->
### RB-1: 
- Alarm / symptoms: 
- Confirm: 
- Mitigate: 
- Verify recovery: 
- Automated remediation: 

## Escalation
<!-- Severity levels with response times, the on-call rotation that is paged first, and who comes next, after how long. -->
| Severity | Response time | First responder (rotation) | Escalate to (after) |
|---|---|---|---|
| SEV1 |  |  |  |
| SEV2 |  |  |  |

## Communication
<!-- During an incident: where it is coordinated, who updates stakeholders and customers and how often, and when the post-incident review is held. -->
