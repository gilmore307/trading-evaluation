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
- `02_feed_alpaca_liquidity` through full trades/quotes over each hourly regular-session window in the component month
- `03_feed_alpaca_news`
- `05_feed_gdelt_news` for broad market, sector, theme, and symbol event evidence
- `07_feed_trading_economics_calendar_web` for high-importance U.S. macro event evidence
- `08_feed_sec_company_financials` for mapped single-name SEC companyfacts evidence
- `09_feed_thetadata_option_selection_snapshot` for daily open, midday, and close option-chain snapshots

Crypto components prepare one-shot acquisition requirements for:

- `04_feed_okx_crypto_market_data`

ThetaData selected-contract feeds (`10_feed_thetadata_option_primary_tracking` and `11_feed_thetadata_option_event_timeline`) are expanded only after the option-chain snapshots have produced concrete expiration/right/strike selections. They are not guessed in the initial bundle.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_benchmark_dataset.py \
  --contract benchmarks/primary_benchmark_candidate_20260519.json \
  --output-root /root/projects/trading-storage/storage/benchmark \
  --data-root /root/projects/trading-data/storage
```

The generated acquisition plan records feed parameters and target output roots only. Live provider calls require a separate one-shot benchmark acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed one-time benchmark artifact.
