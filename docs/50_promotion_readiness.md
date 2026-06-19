# Promotion Readiness

Promotion readiness is evaluation-owned. Runtime activation is execution-owned.

`trading-evaluation` may publish `promotion_readiness_record` after a pinned M01-M06 candidate bundle has passed frozen replay settlement and promotion eligibility checks. This admits the bundle to execution shadow review; it does not switch active configs.

## Required Inputs

- accepted `promotion_eligibility_decision` with `decision_status = eligible`;
- accepted replay contract reference plus `replay_validation_ref` and `replay_freeze_status = frozen`;
- fold settlement run, metric references, `fold_stack_evidence_ref`, and `fold_stack_status = complete_m01_m06`;
- non-empty guardrail refs with `guardrail_status = passed`;
- incumbent comparison ref with `incumbent_comparison_status = passed`; for the first model bootstrap, the comparison ref is the bootstrap baseline settlement run created by evaluation;
- advisory `promotion-evaluation-review` ref with `agent_review_recommendation = eligible_for_shadow`;
- pinned M01-M06 candidate model/config refs;
- rollback ref;
- execution shadow scope.

Agent review can support readiness only through the fixed `promotion-evaluation-review` skill and only as advisory evidence. It cannot directly switch active config pointers.

## Forbidden Side Effects

Promotion readiness records must not activate models, write active model config pointers, place orders, call brokers, mutate accounts, call providers, or perform storage lifecycle mutation.

`trading-execution` consumes promoted readiness records during market-hours shadow cycles and owns active model selection after live/shadow evidence matures.

For `first_model_bootstrap = true`, readiness admits the first promoted bundle into shadow as the initial baseline candidate. It still must not write the active pointer; execution activation remains gated by market-hours shadow evidence and `execution_active_model_config_write`.
