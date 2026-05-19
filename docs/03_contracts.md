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

`promotion_eligibility_decision` states whether settlement evidence makes a candidate eligible for evaluation-owned model activation.

## Model Activation Record

`model_activation_record` records the config release after an eligible promotion decision.

Required fields:

- `promotion_eligibility_decision_ref`
- `activated_model_id`
- `activated_config_ref`
- `active_model_config_ref`
- `rollback_ref`
- `activation_scope`
- `activated_by`
- `activated_at_utc`

It must report `broker_execution_performed = false` and `account_mutation_performed = false`.
