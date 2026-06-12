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
- `base_context_policy_ref`
- `base_context_ref`
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

The validator requires a candidate-policy replay with a valid replay window, positive minimum trading days, sufficient declared market-condition coverage, non-empty candidate policy, replay route, data snapshot, cost model, baseline refs, guardrail refs, selection metric refs, explicit exclusion windows covering the full replay window, `candidate_fold_id`, and a Layer 1/2 `base_context_ref`. `target_symbol`, `target_refs`, and `replay_components` are rejected at the replay-contract boundary. The manager owns model-artifact selection from completed fold state; replay does not carry or consume the training target symbol. `is_training_fold_blocked_by_replay` blocks folds that overlap the sealed replay window.

The accepted `replay_route_ref` is `trading-execution://execution_runtime_component_graph/replay`. Replay calls the execution-owned component graph with Replay adapters; evaluation does not own a separate trading decision graph.

`evaluation_replay_runtime_dry_run` is the fixture-safe harness proving that
evaluation can call the execution-owned Replay route directly. It returns the
execution component graph mode/policy, emitted runtime decision records,
validation results, and safety flags. It must not train models, call providers,
write active model config, submit broker requests, or mutate account state.

`evaluation_replay_execution_run` records a side-effect-free Replay execution
over frozen local base-context artifacts and month-scoped on-demand candidate
artifacts. It calls `trading-execution` runtime builders under Replay adapters,
writes settlement-ready `evaluation_replay_decision_row` JSONL, and records
safety flags proving no broker call, account mutation, model training, or
active config write occurred. Provider calls are allowed only through reviewed
on-demand replay acquisition gates. This is Replay evidence, not a promotion
eligibility decision.

Every replay decision owns an explicit `replay_time_pointer`. Decision inputs
must be available at or before that pointer. Data after the pointer is invalid
for C01-C07 model/execution inputs, including on-demand option-chain evidence.
Future bars, selected-contract path rows, fill settlement, labels, and realized
returns are allowed only after the decision row is emitted and only for
evaluation settlement. They must not feed the same-row decision inputs.

Replay option-expression inputs come from
`trading_data.model_05_option_expression_feature_generation` only after M04 emits
an option-expression handoff for the current replay timestamp. If the manager
records `snapshot_type = source_unavailable` for that exact target/timestamp,
replay treats the option surface as `option_source_unavailable` and continues
with `asset_expression_route = option_expression_unfilled` instead of requesting
future evidence or repeating provider acquisition.

Runtime component artifacts are not replay-specific. Replay uses the same
execution-owned component output contracts as live execution:
`execution_intake_snapshot`, `entry_decision`,
`position_lifecycle_decision`, `option_reexpression_decision`,
`execution_order_intent`, `execution_gate_result`, and
`failure_explanation_packet`. Replay may set adapter metadata such as
`execution_mode = replay`, simulated account refs, fill simulator refs, or
historical-clock refs. It must not create evaluation-owned substitutes for C01-C07
decision artifacts. `evaluation_replay_decision_row` is only a settlement view
over those component outputs.

If a replay selects a listed option contract but the point-in-time option
contract path is unavailable, the settlement view must preserve the selected
contract and mark `option_contract_path_status = missing` and
`return_source = option_contract_path_missing`. That row is a data-coverage
diagnostic, not an executable fill: it must use `fill_status =
simulated_rejected`, zero cost, and no outcome label.

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
- `base_context_policy_ref`
- `base_context_ref`
- `pre_replay_target_refs`
- `candidate_policy_ref`
- `replay_route_ref`
- `replay_window_manifest_ref`
- `feed_acquisition_plan_ref`
- `coverage_summary_ref`
- safety booleans proving no provider calls, SQL mutation, model training, activation, broker execution, or account mutation occurred

The preparation bundle may write files under the `trading-storage/storage/05_replay_datasets/<contract_id>/`, but it does not generate manager task/request rows or reusable task keys. Layer 1/2 base-context source data is canonical historical source data shared with training and retained after replay. Historical provider acquisition for candidate equity, option, liquidity, and symbol-news evidence is a one-shot gated action during replay execution. It may temporarily materialize only the replay month and candidate set required by the current shard, and that on-demand month cache is deleted after the shard writes replay receipts, decision rows, coverage summaries, row counts, and input hashes. Replay must not infer its candidate set by scanning already materialized local bar directories.

After accepted base-context coverage, the replay contract references one frozen evidence snapshot for the explicit fold. All replay and downstream evaluation artifacts for that scope must consume that base snapshot. Candidate-specific long-lived data download, source reinterpretation, or training-flow feature generation is not allowed for replay judgment; candidate and option evidence discovered by C01-C07 is acquired on demand and retained only as lightweight replay evidence after the month shard completes.

`replay_dataset_freeze_receipt` records the accepted storage-side freeze. It requires explicit `pre_replay_target_refs`, local coverage validation, `missing_feed_acquisition_count = 0`, and no missing base-context rows for the explicit fold boundary. It marks the manifest `freeze_status = frozen` and reports safety flags proving no provider calls, SQL mutation, model training, activation, broker execution, or account mutation occurred during freeze.

Replay uses the execution runtime component graph with a historical clock. It consumes point-in-time market, event, liquidity, and account-context inputs from the frozen snapshot and on-demand replay cache, calls the same task-level components used by live execution, and then settles the emitted decision rows. Models are component input evidence; C01-C07 are the execution units. Layer 10 is called only through execution's `failure_explanation_component` after observed model or trade failure; normal entry and lifecycle event risk comes from Layer 4. Option-chain snapshots are requested only when replayed components create buy or option-expression points.

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
