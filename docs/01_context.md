# Context

## Component Map

| Component | Relationship |
| --- | --- |
| `trading-model` | Produces model candidates, model outputs, and model-local evaluation evidence. |
| `trading-evaluation` | Independently evaluates candidates against frozen benchmark contracts and emits fold settlement / promotion eligibility evidence. |
| `trading-manager` | Schedules fold work and records workflow state; it consumes evaluation status but does not own benchmark judgment. |
| `trading-storage` | Stores durable settlement reports, artifacts, refs, archives, and lifecycle evidence. |
| `trading-dashboard` | Displays already-materialized evaluation read models. |
| `trading-execution` | Consumes separately activated decisions for paper/live execution; it is not part of evaluation. |

## Operating Assumptions

- The benchmark target/window is selected once under review and then frozen.
- The benchmark contract records enough data-snapshot, cost-model, baseline, and exclusion evidence to make later fold comparisons reproducible.
- Guardrail benchmarks may block overfit or pathological candidates, but the primary benchmark remains the main horizontal comparison surface.
- Settlement reports must separate returns from risk, turnover, abstention quality, event-risk intervention effect, and calibration.

