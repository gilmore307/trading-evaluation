# Benchmark Dataset Preparation

`benchmark_dataset_preparation_manifest` is the storage-side one-shot acquisition bundle for an accepted candidate-policy replay benchmark.

The preparation step writes runtime artifacts under `trading-storage/storage/benchmark_datasets/<contract_id>/`:

- `dataset_manifest.json`
- `replay_window_manifest.csv`
- `feed_acquisition_plan.csv`
- `coverage_summary.csv`

This step is not a benchmark freeze and does not use the manager task/request route. It performs no provider calls, SQL mutation, model training, activation, broker execution, or account mutation.

## Current Inputs

- source contract: pending accepted candidate-policy replay benchmark under `trading-evaluation/benchmarks/`
- canonical replay window: `2021-01-01` through `2026-01-01` end-exclusive
- local coverage scan root: `trading-storage/storage/source_data`
- runtime output root: `trading-storage/storage/benchmark_datasets`

## Feed Requirements

Candidate-policy replay prepares one-shot acquisition requirements for the full replay window:

- `01_feed_alpaca_bars`
- `02_feed_alpaca_liquidity`
- `03_feed_alpaca_news`
- `05_feed_gdelt_news` for broad market, sector, theme, and symbol event evidence
- `07_feed_trading_economics_calendar_web` for high-importance U.S. macro event evidence
- `04_feed_okx_crypto_market_data`

Candidate symbols are not preselected. The candidate universe materializes point-in-time during replay from the accepted candidate policy. ThetaData option-chain snapshots (`09_feed_thetadata_option_selection_snapshot`) are generated on demand from benchmark replay model buy/expression points. Selected-contract feeds (`10_feed_thetadata_option_primary_tracking` and `11_feed_thetadata_option_event_timeline`) expand only after those snapshots produce concrete expiration/right/strike selections. They are not guessed or pre-scanned across every benchmark day in the initial bundle.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_benchmark_dataset.py \
  --contract benchmarks/promotion_benchmark_candidate_policy_replay.json \
  --output-root /root/projects/trading-storage/storage/benchmark_datasets \
  --data-root /root/projects/trading-storage/storage/source_data
```

The generated acquisition plan records feed parameters and target output roots only. Live provider calls require a separate one-shot benchmark acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed one-time benchmark artifact.

## Reusable Frozen Snapshot

Benchmark data acquisition, event evidence collection, and source normalization are one-time dataset construction phases. Once the acquisition plan reaches accepted coverage and the benchmark is frozen, storage records one reusable benchmark data snapshot for the contract.

All benchmark replay, fold settlement, promotion eligibility comparison, guardrail replay, and later regression checks must reference that frozen snapshot. They must not re-download, re-sample, reinterpret, or rebuild benchmark data per model candidate. If the benchmark dataset is wrong or incomplete, the fix is a new reviewed benchmark data snapshot or a new benchmark contract, not candidate-specific data preparation.

Benchmark evaluation uses the realtime execution decision path under a historical clock. The runner should feed the frozen point-in-time market, event, liquidity, and account-context inputs through the same route used for live/shadow decision making. It must not use the model training pipeline or any training feature-generation route as the benchmark execution path.

ThetaData option-chain snapshots remain replay-triggered. During historical realtime replay, a model buy or option-expression decision creates the point-in-time option snapshot request; selected-contract tracking expands from the concrete expiration/right/strike result. This keeps the benchmark close to live behavior while preserving one frozen underlying/event/liquidity data substrate.

To plan or execute bounded one-shot acquisitions from the generated plan:

```bash
PYTHONPATH=src python3 scripts/evaluation/run_benchmark_acquisition.py \
  --dataset-root /root/projects/trading-storage/storage/benchmark_datasets/promotion_benchmark_candidate_policy_replay \
  --source-id gdelt_news \
  --limit 10
```

Add `--execute` only when live provider acquisition should run. The runner writes one-shot task payloads and progress logs under the benchmark dataset root and still does not create manager request rows.
