# Contracts

## Replay Contract

`evaluation_replay_contract` is the contract type for the frozen replay surface:

Canonical SQL table:

```text
trading_evaluation.replay_contract
```

- `contract_id`
- `replay_mode = candidate_policy_replay`
- `candidate_fold_id`
- `tradable_universe_policy_ref`
- `tradable_universe_ref`
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

The validator requires a candidate-policy replay with a valid replay window, positive minimum trading days, sufficient declared market-condition coverage, non-empty candidate policy, replay route, data snapshot, cost model, baseline refs, guardrail refs, selection metric refs, explicit exclusion windows covering the full replay window, `candidate_fold_id`, and a live-equivalent `tradable_universe_ref`. `target_symbol`, `target_refs`, and `replay_components` are rejected at the replay-contract boundary. The manager owns model-artifact selection from completed fold state; replay does not carry or consume the training target symbol. `is_training_fold_blocked_by_replay` blocks folds that overlap the sealed replay window.

The accepted `replay_route_ref` is `trading-execution://execution_runtime_component_graph/replay`. Replay calls the execution-owned component graph with Replay adapters; evaluation does not own a separate trading decision graph.

`evaluation_replay_runtime_dry_run` is the fixture-safe harness proving that
evaluation can call the execution-owned Replay route directly. It returns the
execution component graph mode/policy, emitted runtime decision records,
validation results, and safety flags. It must not train models, call providers,
write active model config, submit broker requests, or mutate account state.

`evaluation_replay_execution_run` records a side-effect-free Replay execution
over frozen local source artifacts for the live-equivalent `tradable_target_refs`
declared by the replay dataset. It calls
`trading-execution` runtime builders under Replay adapters, writes
settlement-ready `evaluation_replay_decision_row` JSONL, and records safety
flags proving no provider call, broker call, account mutation, model training,
or active config write occurred. This is Replay evidence, not a promotion
eligibility decision.

Canonical SQL tables:

```text
trading_evaluation.replay_execution_run
trading_evaluation.replay_decision
trading_evaluation.replay_progress
```

## Replay Dataset Preparation Manifest

`replay_dataset_preparation_manifest` is the contract type for the runtime preparation bundle for a replay contract under storage ownership.

Canonical SQL tables:

```text
trading_evaluation.replay_dataset_preparation
trading_evaluation.replay_dataset_freeze
trading_evaluation.replay_source_coverage
```

Required fields include:

- `contract_id`
- `preparation_status`
- `freeze_status`
- `source_contract_ref`
- `dataset_root`
- `candidate_fold_id`
- `tradable_universe_policy_ref`
- `tradable_universe_ref`
- `tradable_target_refs`
- `candidate_policy_ref`
- `replay_route_ref`
- `replay_window_manifest_ref`
- `feed_acquisition_plan_ref`
- `coverage_summary_ref`
- safety booleans proving no provider calls, SQL mutation, model training, activation, broker execution, or account mutation occurred

The preparation bundle may write files under the `trading-storage/storage/05_replay_datasets/<contract_id>/`, but it does not generate manager task/request rows or reusable task keys. Historical provider acquisition for the sealed replay is a one-shot gated action. It may temporarily materialize only the replay month and candidate set required by the current shard, and the month cache is deleted after the shard writes replay receipts, decision rows, coverage summaries, row counts, and input hashes. Replay must not infer its candidate universe by scanning already materialized local bar directories.

After accepted acquisition coverage, the replay contract references one frozen evidence snapshot for the explicit fold and live-equivalent tradable universe scope. All replay and downstream evaluation artifacts for that scope must consume that snapshot. Candidate-specific long-lived data download, source reinterpretation, or training-flow feature generation is not allowed for replay judgment.

`replay_dataset_freeze_receipt` records the accepted storage-side freeze. It requires explicit `tradable_target_refs`, local coverage validation, `missing_feed_acquisition_count = 0`, and only accepted deferred source ids for the explicit fold and tradable-universe acquisition boundary. It marks the manifest `freeze_status = frozen` and reports safety flags proving no provider calls, SQL mutation, model training, activation, broker execution, or account mutation occurred.

Replay uses the execution runtime component graph with a historical clock. It consumes point-in-time market, event, liquidity, and account-context inputs from the frozen snapshot, calls the same task-level components used by live/shadow execution, and then settles the emitted decision rows. Layer 10 is called only through execution's `failure_explanation_component` after observed model or trade failure; normal entry and lifecycle event risk comes from Layer 4. Option-chain snapshots are requested only when replayed model decisions create buy or option-expression points.

## Fold Settlement Run

`fold_settlement_run` summarizes one completed fold against one accepted replay contract.

Canonical SQL tables:

```text
trading_evaluation.fold_settlement_run
trading_evaluation.fold_settlement_metric
```

Required run fields:

- `contract_type = fold_settlement_run`
- `fold_settlement_run_id`
- `fold_id`
- `candidate_model_ref`
- `replay_contract_ref`
- `replay_result_ref`
- `baseline_ref`
- `created_at_utc`
- `decision_status` in `passed`, `review_required`, or `failed`
- `gate_failures`
- `metric_refs`
- `metrics`
- `agent_review_required = true`
- `agent_review_scope = promotion-evaluation-review`
- safety booleans proving no model activation, active config write, broker execution, or account mutation occurred

Required metric fields:

- `contract_type = fold_settlement_metric`
- `settlement_run_ref`
- `decision_row_count`
- `net_return_total`
- `baseline_return_total`
- `excess_return_total`
- `max_drawdown`
- `turnover_proxy_count`
- `hit_rate`
- `payoff_ratio`
- `auroc`
- `auroc_pair_count`
- `brier_score`
- `feature_column_count`
- `feature_row_count`
- `pca_available`
- `pcoa_available`

The validator requires the metric ref to match the settlement run, core metric fields to be present and typed, bounded probability metrics to stay within `0..1`, and deterministic gate failures to be present when evidence is too small, AUROC is unavailable/weak, or net return is not above baseline.

## Promotion Eligibility Decision

`promotion_eligibility_decision` states whether settlement evidence makes a candidate eligible for execution shadow review.

Canonical SQL table:

```text
trading_evaluation.promotion_eligibility_decision
```

An `eligible` decision must include frozen replay validation evidence, complete Layer 1-10 fold-stack evidence, non-empty metric refs, passed guardrail evidence, incumbent comparison evidence, and advisory `promotion-evaluation-review` evidence with `agent_review_recommendation = eligible_for_shadow`. For the first accepted model bundle, `first_model_bootstrap = true` allows the candidate's own frozen settlement run to serve as the bootstrap baseline for later anonymous incumbent comparisons.

Agent review evidence may support this decision only when it follows the fixed `promotion-evaluation-review` skill. The review is advisory and must not change the sealed replay, write active config pointers, or replace deterministic validation.

## Promotion Readiness Record

`promotion_readiness_record` admits an eligible candidate to execution-owned shadow review.

Canonical SQL tables:

```text
trading_evaluation.promotion_readiness_record
trading_evaluation.promoted_model_parameter
```

Required fields:

- `promotion_eligibility_decision_ref`
- `candidate_model_ref`
- `candidate_config_ref`
- `rollback_ref`
- `execution_shadow_scope`
- `replay_contract_ref`
- `replay_validation_ref`
- `replay_freeze_status = frozen`
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
- optional `first_model_bootstrap = true` with `bootstrap_baseline_ref` for the first promoted baseline only
- `created_at_utc`

It must report `model_activation_performed = false`, `active_model_config_written = false`, `broker_execution_performed = false`, and `account_mutation_performed = false`.
