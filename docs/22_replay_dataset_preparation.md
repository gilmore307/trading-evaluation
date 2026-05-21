# Replay Dataset Preparation

`replay_dataset_preparation_manifest` is the contract type for the storage-side one-shot acquisition bundle for an accepted candidate-policy replay.

The preparation step writes runtime artifacts under `trading-storage/storage/05_replay_datasets/<contract_id>/`:

- `dataset_manifest.json`
- `replay_window_manifest.csv`
- `feed_acquisition_plan.csv`
- `coverage_summary.csv`

This step is not a replay freeze and does not use the manager task/request route. It performs no provider calls, SQL mutation, model training, activation, broker execution, or account mutation.

## Current Inputs

- source contract: pending accepted candidate-policy replay under `trading-evaluation/replays/`
- canonical replay window: `2021-01-01` through `2026-01-01` end-exclusive
- local coverage scan root: `trading-storage/storage/01_source_data`
- runtime output root: `trading-storage/storage/05_replay_datasets`

## Feed Requirements

Candidate-policy replay prepares one-shot acquisition requirements for the full replay window:

- `01_feed_alpaca_bars`
- `02_feed_alpaca_liquidity`
- `03_feed_alpaca_news`
- `05_feed_gdelt_news` for broad market, sector, theme, and symbol event evidence
- `07_feed_trading_economics_calendar_web` for high-importance U.S. macro event evidence
- `04_feed_okx_crypto_market_data`

Candidate symbols are not preselected. The candidate universe materializes point-in-time during replay from the accepted candidate policy. ThetaData option-chain snapshots (`09_feed_thetadata_option_selection_snapshot`) are generated on demand from replayed model buy/expression points. Selected-contract feeds (`10_feed_thetadata_option_primary_tracking` and `11_feed_thetadata_option_event_timeline`) expand only after those snapshots produce concrete expiration/right/strike selections. They are not guessed or pre-scanned across every replay day in the initial bundle.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_replay_dataset.py \
  --contract replays/promotion_replay_candidate_policy.json \
  --output-root /root/projects/trading-storage/storage/05_replay_datasets \
  --data-root /root/projects/trading-storage/storage/01_source_data
```

The generated acquisition plan records feed parameters and target output roots only. Live provider calls require a separate one-shot replay acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed one-time replay artifact.

## Reusable Frozen Snapshot

Replay data acquisition, event evidence collection, and source normalization are one-time dataset construction phases. Once the acquisition plan reaches accepted coverage and the replay is frozen, storage records one reusable replay data snapshot for the contract.

All replay, fold settlement, promotion eligibility comparison, guardrail replay, and later regression checks must reference that frozen snapshot. They must not re-download, re-sample, reinterpret, or rebuild replay data per model candidate. If the replay dataset is wrong or incomplete, the fix is a new reviewed replay data snapshot or a new replay contract, not candidate-specific data preparation.

Replay evaluation uses `trading-execution`'s `execution_runtime_component_graph` under a historical clock and Replay adapters. The runner should feed the frozen point-in-time market, event, liquidity, and account-context inputs through the same task-level components used for live/shadow decision making. It must not use the model training pipeline, a training feature-generation route, or a separate evaluation-owned decision graph as the replay execution path. Layer 10 is reached only through the Failure Explanation Component after observed model or trade failure.

ThetaData option-chain snapshots remain replay-triggered. During historical realtime replay, a model buy or option-expression decision creates the point-in-time option snapshot request; selected-contract tracking expands from the concrete expiration/right/strike result. This keeps replay close to live behavior while preserving one frozen underlying/event/liquidity data substrate.

To plan or execute bounded one-shot acquisitions from the generated plan:

```bash
PYTHONPATH=src python3 scripts/evaluation/run_replay_acquisition.py \
  --dataset-root /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy \
  --source-id gdelt_news \
  --limit 10
```

Add `--execute` only when live provider acquisition should run. The runner writes one-shot task payloads and progress logs under the replay dataset root and still does not create manager request rows.
