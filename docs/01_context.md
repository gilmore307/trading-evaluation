# Context

## Component Map

| Component | Relationship |
| --- | --- |
| `trading-model` | Produces model candidates, model outputs, and model-local evaluation evidence. |
| `trading-evaluation` | Independently evaluates candidates against frozen replay contracts and emits fold settlement, promotion eligibility, and promotion readiness evidence. |
| `trading-execution` | Owns the runtime component graph used by live/shadow execution and Replay; also owns runtime active model selection after shadow evidence matures. |
| `trading-manager` | Schedules fold work and records workflow state; it consumes evaluation/execution status but does not own replay judgment or activation. |
| `trading-storage` | Stores durable settlement reports, artifacts, refs, archives, and lifecycle evidence. |
| `trading-dashboard` | Displays already-materialized evaluation read models. |

## Operating Assumptions

- The promotion replay is selected once under review and then frozen as a candidate-policy replay over `2021-01-01` through `2026-01-01` end-exclusive.
- The replay contract records enough data-snapshot, cost-model, baseline, and exclusion evidence to make later fold comparisons reproducible.
- Replay calls `trading-execution`'s `execution_runtime_component_graph` with Replay adapters; evaluation owns the judgment, not the trading decisions.
- Guardrail replays may block overfit or pathological candidates, but the primary replay remains the main horizontal comparison surface.
- Settlement reports must separate returns from risk, turnover, abstention quality, event-risk intervention effect, and calibration.
- Promotion readiness records admit candidates to execution shadow review; execution owns runtime active model selection and remains the broker/account boundary.
