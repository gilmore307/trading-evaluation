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

`promotion_eligibility_decision` will state whether settlement evidence makes a candidate eligible for a later activation gate.

It must never activate a production model by itself.

