# Benchmark Dataset Preparation

`benchmark_dataset_preparation_manifest` is the storage-side preparation bundle for an accepted benchmark contract candidate.

The preparation step writes runtime artifacts under `trading-storage/storage/benchmark/<contract_id>/`:

- `dataset_manifest.json`
- `component_manifest.csv`
- `feed_task_plan.csv`
- `coverage_summary.csv`
- fail-closed provider task keys under `task_keys/`

This step is not a benchmark freeze. It performs no provider calls, SQL mutation, model training, activation, broker execution, or account mutation.

## Current Inputs

- source contract: `trading-evaluation/benchmarks/primary_benchmark_candidate_20260519.json`
- shared candidate CSV: `trading-storage/main/shared/evaluation_primary_benchmark_candidate.csv`
- local coverage scan root: `trading-data/storage`
- runtime output root: `trading-storage/storage/benchmark`

## Feed Requirements

Equity single-name and ETF components prepare fail-closed task keys for:

- `01_feed_alpaca_bars`
- `02_feed_alpaca_liquidity`
- `03_feed_alpaca_news`

Crypto components prepare fail-closed task keys for:

- `04_feed_okx_crypto_market_data`

ThetaData selected-contract feeds are deliberately deferred until option contract selection exists for each component window. SEC company-financial task keys are deferred until target-context review supplies CIK mappings. These are recorded in `known_deferred_requirements` instead of being guessed.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_benchmark_dataset.py \
  --contract benchmarks/primary_benchmark_candidate_20260519.json \
  --output-root /root/projects/trading-storage/storage/benchmark \
  --data-root /root/projects/trading-data/storage
```

The generated task keys set `manager_controls.allow_live_provider_calls = false`. Provider dispatch requires a separate manager/provider execution gate.
