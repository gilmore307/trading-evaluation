# Contracts

## Benchmark Contract

`evaluation_benchmark_contract` defines the frozen evaluation surface:

- `contract_id`
- `target_symbol`
- `start_date`
- `end_date`
- `min_trading_days`
- `market_condition_tags`
- `data_snapshot_ref`
- `cost_model_ref`
- `baseline_refs`
- `training_universe_symbols`
- `excluded_training_windows`
- `guardrail_refs`

The current validator requires a non-empty target, chronological date range, sufficient declared market-condition coverage, non-empty baseline refs, and proof that the target is not in the training universe.

## Fold Settlement Run

`fold_settlement_run` will summarize one completed fold against one accepted benchmark contract.

Required future fields:

- `fold_id`
- `benchmark_contract_id`
- `candidate_model_refs`
- `baseline_refs`
- `metric_refs`
- `report_ref`
- `validation_status`
- `generated_at_utc`

## Promotion Eligibility Decision

`promotion_eligibility_decision` states whether settlement evidence makes a candidate eligible for execution shadow review.

Agent review evidence may support this decision only when it follows the fixed `promotion-evaluation-review` skill. The review is advisory and must not change the sealed benchmark, write active config pointers, or replace deterministic validation.

## Promotion Readiness Record

`promotion_readiness_record` admits an eligible candidate to execution-owned shadow review.

Required fields:

- `promotion_eligibility_decision_ref`
- `candidate_model_ref`
- `candidate_config_ref`
- `rollback_ref`
- `execution_shadow_scope`
- `created_at_utc`

It must report `model_activation_performed = false`, `active_model_config_written = false`, `broker_execution_performed = false`, and `account_mutation_performed = false`.
