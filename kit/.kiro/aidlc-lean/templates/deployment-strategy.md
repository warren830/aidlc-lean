# Deployment Strategy: {{TITLE}}

AI-DLC stage: Operations · Deployment Pipeline · Intent: {{INTENT}}
<!-- Optional. Run it when the CD pipeline is new or this release changes how it goes out. One page about how the team's CI/CD (e.g. GitLab, then Argo CD) deploys: the agent writes this page and the config; it never runs a deployment. Build on infrastructure-design.md and ci-config.md where they exist, and describe the real pipeline, not an invented one. -->

## CD Configuration
<!-- The CD tool, the config files and their paths (manifests, Helm values, the Argo application), what triggers a deployment, and which artifact it takes. -->

## Strategy
<!-- Rolling, blue/green or canary, and why. Canary: the steps (e.g. 5 % -> 25 % -> 100 %) and what must hold before each next step. Database migrations: before or after the code, and backward compatible? -->

## Environment Promotion
| From -> to | Gate (tests, metrics, wait) | Approved by | Automatic? |
|---|---|---|---|
| dev -> staging |  |  |  |
| staging -> prod |  |  |  |

## Feature Flags
<!-- Flags that guard the new behaviour: name, default per environment, who switches them, when they are removed. Write "none" if none. -->

## Rollback
<!-- The rollback runbook, for the person on duty. Trigger: the signals and thresholds (alarms in observability.md). Steps: exact, in the team's tooling (e.g. revert the commit and let CD sync, roll back the Argo application, switch the flag off). Data: how a migration is undone or rolled forward. -->
- Trigger: 
- Decided by: 
- Steps: 
- Data and migrations: 
- Time to roll back: 
- Confirm it worked: 
