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
- `excluded_training_windows` covering the full replay window

The current validator requires a candidate-policy replay benchmark over the canonical fixed window `2021-01-01` through `2026-01-01` end-exclusive, with at least 1255 expected trading days, sufficient declared market-condition coverage, non-empty candidate policy, replay route, data snapshot, cost model, baseline refs, guardrail refs, selection metric refs, and explicit exclusion windows covering the full replay window. Fixed target fields and `benchmark_components` are rejected. `is_training_fold_blocked_by_benchmark` is the reusable helper for blocking folds that overlap the sealed replay window.

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

The preparation bundle may write files under `trading-storage/storage/05_benchmark_datasets/<contract_id>/`, but it does not generate manager task/request rows or reusable task keys. Live provider acquisition for the sealed benchmark is a one-shot gated action that records receipts under the source storage roots.

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

An `eligible` decision must include frozen benchmark validation evidence, complete Layer 1-10 fold-stack evidence, non-empty metric refs, passed guardrail evidence, incumbent comparison evidence, and advisory `promotion-evaluation-review` evidence with `agent_review_recommendation = eligible_for_shadow`.

Agent review evidence may support this decision only when it follows the fixed `promotion-evaluation-review` skill. The review is advisory and must not change the sealed benchmark, write active config pointers, or replace deterministic validation.

## Promotion Readiness Record

`promotion_readiness_record` admits an eligible candidate to execution-owned shadow review.

Required fields:

- `promotion_eligibility_decision_ref`
- `candidate_model_ref`
- `candidate_config_ref`
- `rollback_ref`
- `execution_shadow_scope`
- `benchmark_contract_ref`
- `benchmark_validation_ref`
- `benchmark_freeze_status = frozen`
- `settlement_run_ref`
- non-empty `metric_refs`
- `fold_stack_evidence_ref`
- `fold_stack_status = complete_layer_01_10`
- non-empty `guardrail_refs`
- `guardrail_status = passed`
- `incumbent_comparison_ref`
- `incumbent_comparison_status = passed`
- `agent_review_ref`
- `agent_review_recommendation = eligible_for_shadow`
- `created_at_utc`

It must report `model_activation_performed = false`, `active_model_config_written = false`, `broker_execution_performed = false`, and `account_mutation_performed = false`.
