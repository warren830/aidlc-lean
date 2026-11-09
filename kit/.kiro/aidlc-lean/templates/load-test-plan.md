# Load Test Plan: {{TITLE}}

AI-DLC stage: Operations · Performance Validation · Intent: {{INTENT}}
<!-- Optional. Run it when performance targets need proving under load. One page: the plan, then the results against each target. The load script is product code; a person or the team's pipeline runs it against a shared environment, never the agent. Record the results they report. -->

## NFR Targets
<!-- One row per performance or scalability target in "Non-functional targets" of requirements.md (and nfr-design.md), the value copied exactly (e.g. "p95 < 300 ms at 50 rps"). Every row names the scenario that tests it. -->
| Target (requirements.md) | Value | Scenario | Pass when |
|---|---|---|---|
|  |  | S-1 |  |

## Scenarios
<!-- Steady state, peak, burst, soak. Per scenario: the user journey or endpoints, the load shape (rate or users, ramp), duration, and the test data. -->
| ID | Journey / endpoints | Load shape | Duration | Data |
|---|---|---|---|---|
| S-1 |  |  |  |  |

## Environment and Tools
<!-- Where it runs (production-like: say how it differs from prod), the tool and the script's path, and the dashboards from observability.md that are watched. -->

## Results
<!-- After the run: target vs. actual, from the tool's report and the dashboards; link the raw report. -->
| Target | Value | Actual | Met? | Evidence |
|---|---|---|---|---|
|  |  |  | yes / no |  |

## Bottlenecks and Capacity
<!-- What limited throughput first (CPU, database connections, a downstream call), how auto-scaling behaved, and the capacity needed for the expected peak. -->
