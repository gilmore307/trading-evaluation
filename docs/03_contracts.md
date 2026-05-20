# Contracts

## Benchmark Contract

`evaluation_benchmark_contract` defines the frozen evaluation surface:

- `contract_id`
- `benchmark_mode = candidate_policy_replay`
- `start_date`
- `end_date`
- `min_trading_days`
- `market_condition_tags`
- `candidate_policy_ref`
- `replay_route_ref`
- `data_snapshot_ref`
- `cost_model_ref`
- `baseline_refs`
- `guardrail_refs`
- `selection_metric_refs`
- `excluded_training_windows` covering the full two-year replay window

The current validator requires a candidate-policy replay benchmark, chronological date ranges, at least two calendar years, at least 504 expected trading days, sufficient declared market-condition coverage, non-empty candidate policy, replay route, data snapshot, cost model, baseline refs, guardrail refs, selection metric refs, and explicit exclusion windows covering the full replay window. Fixed target fields and `benchmark_components` are rejected. `is_training_fold_blocked_by_benchmark` is the reusable helper for blocking folds that overlap the sealed replay window.

## Benchmark Dataset Preparation Manifest

`benchmark_dataset_preparation_manifest` records the runtime preparation bundle for a benchmark contract under storage ownership.

Required fields include:

- `contract_id`
- `preparation_status`
- `freeze_status`
- `source_contract_ref`
- `dataset_root`
- `candidate_policy_ref`
- `replay_route_ref`
- `replay_window_manifest_ref`
- `feed_acquisition_plan_ref`
- `coverage_summary_ref`
- safety booleans proving no provider calls, SQL mutation, model training, activation, broker execution, or account mutation occurred

The preparation bundle may write files under `trading-storage/storage/benchmark/<contract_id>/`, but it does not generate manager task/request rows or reusable task keys. Live provider acquisition for the sealed benchmark is a one-shot gated action that records receipts under the source storage roots.

After accepted acquisition coverage, the benchmark contract references one frozen reusable data snapshot. All benchmark replay and downstream evaluation artifacts for that contract must consume that snapshot. Candidate-specific data download, source reinterpretation, or training-flow feature generation is not allowed for benchmark judgment.

Benchmark replay uses the realtime execution route with a historical clock. It consumes point-in-time market, event, liquidity, and account-context inputs from the frozen snapshot, then requests option-chain snapshots only when replayed model decisions create buy or option-expression points.

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
