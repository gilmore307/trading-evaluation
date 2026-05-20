# Contracts

## Benchmark Contract

`evaluation_benchmark_contract` defines the frozen evaluation surface:

- `contract_id`
- `benchmark_components` with anonymous component id, target symbol, asset class, theme bucket, component role, start/end window, weight, market-condition tags, data-availability tags, target-context ref where required, and stress-exception ref where required
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

The current validator requires at least one benchmark component, chronological date ranges, asset class and theme bucket metadata, positive component weights, sufficient declared market-condition coverage, non-empty baseline refs, and explicit exclusion windows covering every component's target/window. Single-name equity and crypto components require a reviewed target-context ref so non-ETF targets still route through accepted target-context/proxy review. Controlled stress components may model critical data gaps such as crypto missing quote/order-book context, missing Layer 2 context, or intentionally missing target context only when `component_role` is `stress_edge_case` or `guardrail_stress`, `stress_exception_ref` is present, and aggregate stress weight stays within the accepted cap. When a benchmark component uses a target over a time window, same-target training folds that overlap that window are contaminated and must be skipped or blocked. `is_training_fold_blocked_by_benchmark` is the reusable helper for that target/window check.

## Benchmark Dataset Preparation Manifest

`benchmark_dataset_preparation_manifest` records the runtime preparation bundle for a benchmark contract under storage ownership.

Required fields include:

- `contract_id`
- `preparation_status`
- `freeze_status`
- `source_contract_ref`
- `shared_candidate_csv_ref`
- `dataset_root`
- `component_manifest_ref`
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
