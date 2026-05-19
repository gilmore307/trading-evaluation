# Contracts

## Benchmark Contract

`evaluation_benchmark_contract` defines the frozen evaluation surface:

- `contract_id`
- `benchmark_components` with anonymous component id, target symbol, asset class, theme bucket, start/end window, weight, market-condition tags, and target-context ref where required
- `start_date`
- `end_date`
- `min_trading_days`
- `market_condition_tags`
- `data_snapshot_ref`
- `cost_model_ref`
- `baseline_refs`
- `training_universe_symbols`
- `excluded_training_windows` keyed by target/window
- `guardrail_refs`

The current validator requires at least one benchmark component, chronological date ranges, asset class and theme bucket metadata, positive component weights, sufficient declared market-condition coverage, non-empty baseline refs, and explicit exclusion windows covering every component's target/window. Single-name equity and crypto components require a reviewed target-context ref so non-ETF targets still route through accepted target-context/proxy review. When a benchmark component uses a target over a time window, same-target training folds that overlap that window are contaminated and must be skipped or blocked. `is_training_fold_blocked_by_benchmark` is the reusable helper for that target/window check.

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
