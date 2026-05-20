# Promotion Readiness

Promotion readiness is evaluation-owned. Runtime activation is execution-owned.

`trading-evaluation` may publish `promotion_readiness_record` after a pinned Layer 1-10 candidate bundle has passed frozen benchmark settlement and promotion eligibility checks. This admits the bundle to execution shadow review; it does not switch active configs.

## Required Inputs

- accepted `promotion_eligibility_decision` with `decision_status = eligible`;
- accepted benchmark contract reference;
- fold settlement run and metric references;
- pinned Layer 1-10 candidate model/config refs;
- rollback ref;
- execution shadow scope.

Agent review can support readiness only through the fixed `promotion-evaluation-review` skill and only as advisory evidence. It cannot directly switch active config pointers.

## Forbidden Side Effects

Promotion readiness records must not activate models, write active model config pointers, place orders, call brokers, mutate accounts, call providers, or perform storage lifecycle mutation.

`trading-execution` consumes promoted readiness records during market-hours shadow cycles and owns active model selection after live/shadow evidence matures.
