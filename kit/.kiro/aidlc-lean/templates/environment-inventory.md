# Environment Inventory: {{TITLE}}

AI-DLC stage: Operations · Environment Provisioning · Intent: {{INTENT}}
<!-- Optional. Run it when environments are new or change. One page: which environments exist, how they were provisioned, and how they were checked. The IaC is product code from Code Generation; the team's pipeline applies it, never the agent. No secrets and no full account ids: name the secret store entry, and give at most the last 4 digits of an account. -->

## Environments
| Environment | Account / project (last 4) · region | Cluster / namespace or stack | Provisioned by (IaC path, pipeline) | Owner |
|---|---|---|---|---|
| dev |  |  |  |  |
| staging |  |  |  |  |
| prod |  |  |  |  |

## Network and Access
<!-- Per environment, where it differs: VPC and subnets, security groups or network policies, ingress and who can reach it, cross-account or cross-VPC links. -->

## Configuration and Secrets
<!-- Config that differs per environment, and where each secret comes from, by name (secret manager entry, parameter, vault path, CI variable). -->
| Name | Config / secret | Source (by name) | dev / staging / prod |
|---|---|---|---|
|  |  |  |  |

## Validation
<!-- How each environment was checked after provisioning, and by whom: the IaC plan or diff reviewed, health checks, connectivity, secrets resolve. -->
| Environment | Check | Result | Date / by |
|---|---|---|---|
|  |  |  |  |
