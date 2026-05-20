# Benchmark Dataset Preparation

`benchmark_dataset_preparation_manifest` is the storage-side one-shot acquisition bundle for an accepted benchmark contract candidate.

The preparation step writes runtime artifacts under `trading-storage/storage/benchmark/<contract_id>/`:

- `dataset_manifest.json`
- `component_manifest.csv`
- `feed_acquisition_plan.csv`
- `coverage_summary.csv`

This step is not a benchmark freeze and does not use the manager task/request route. It performs no provider calls, SQL mutation, model training, activation, broker execution, or account mutation.

## Current Inputs

- source contract: `trading-evaluation/benchmarks/primary_benchmark_candidate_20260519.json`
- shared candidate CSV: `trading-storage/main/shared/evaluation_primary_benchmark_candidate.csv`
- local coverage scan root: `trading-data/storage`
- runtime output root: `trading-storage/storage/benchmark`

## Feed Requirements

Equity single-name and ETF components prepare one-shot acquisition requirements for:

- `01_feed_alpaca_bars`
- `02_feed_alpaca_liquidity` through full IEX trades/quotes over each weekday regular-session window in the component month
- `03_feed_alpaca_news`

Crypto components prepare one-shot acquisition requirements for:

- `04_feed_okx_crypto_market_data`

ThetaData selected-contract feeds are deliberately deferred until option contract selection exists for each component window. SEC company-financial acquisition is deferred until target-context review supplies CIK mappings. These are recorded in `known_deferred_requirements` instead of being guessed.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_benchmark_dataset.py \
  --contract benchmarks/primary_benchmark_candidate_20260519.json \
  --output-root /root/projects/trading-storage/storage/benchmark \
  --data-root /root/projects/trading-data/storage
```

The generated acquisition plan records feed parameters and target output roots only. Live provider calls require a separate one-shot benchmark acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed one-time benchmark artifact.
