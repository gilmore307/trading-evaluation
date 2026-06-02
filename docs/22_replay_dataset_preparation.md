# Replay Dataset Preparation

`replay_dataset_preparation_manifest` is the contract type for the storage-side one-shot acquisition bundle for an accepted candidate-policy replay.

The preparation step writes runtime artifacts under `trading-storage/storage/05_replay_datasets/<contract_id>/`:

- `dataset_manifest.json`
- `replay_window_manifest.csv`
- `feed_acquisition_plan.csv`
- `coverage_summary.csv`

This preparation step is not a replay freeze and does not use the manager task/request route. It performs no provider calls, SQL mutation, model training, activation, broker execution, or account mutation. The freeze step is a separate storage-side contract mutation that validates coverage, writes `replay_freeze_receipt.json`, and marks the manifest `freeze_status = frozen`.

## Current Inputs

- source contract: accepted candidate-policy replay under `trading-evaluation/replays/`
- replay window: canonical `2021-01-01` through `2026-01-01` end-exclusive unless an explicitly reviewed exception is supplied
- candidate fold id and training target context: explicit, for example `fold_2016-01_2016-06` and `training_target_ref=AAPL`
- tradable universe artifact: explicit, live-equivalent candidate universe used by replay trading decisions
- local coverage scan root: `trading-storage/storage/01_source_data`
- runtime output root: `trading-storage/storage/05_replay_datasets`

## Feed Requirements

Candidate-policy replay prepares one-shot acquisition requirements for the full replay window:

- `01_feed_alpaca_bars`
- `02_feed_alpaca_liquidity`
- `03_feed_alpaca_news`
- `05_feed_gdelt_news` for broad market, sector, theme, and symbol event evidence
- `07_feed_trading_economics_calendar_web` for high-importance U.S. macro event evidence through logged-out visible-page custom-date requests
- `04_feed_okx_crypto_market_data` only when the explicit tradable universe includes crypto targets

Replay tradable refs are predeclared by `tradable_universe_ref` and expanded into `tradable_target_refs` in the dataset manifest and every target-dependent feed row. Replay must not infer its universe by scanning already materialized local bar directories. For an equity target admitted by that universe, Alpaca bars, liquidity, and news rows carry that row's `target_ref`; the execution runner uses the manifest `tradable_target_refs` to restrict market-bar loading. ThetaData option-chain snapshots (`09_feed_thetadata_option_selection_snapshot`) are generated on demand from replayed model buy/expression points. Selected-contract feeds (`10_feed_thetadata_option_primary_tracking` and `11_feed_thetadata_option_event_timeline`) expand only after those snapshots produce concrete expiration/right/strike selections.

## Replay Acquisition Boundary

Replay acquisition is bounded by the historical replay clock, candidate policy, and monthly shard budget:

- preflight may query or estimate source coverage, request counts, row counts, and storage footprint before provider execution;
- provider execution may temporarily materialize only the month and candidate set required by the replay shard;
- temporary month-cache data lives under the replay dataset/run boundary, not under canonical long-lived monthly backfill source roots;
- raw provider payloads are not persisted unless a source contract explicitly requires raw evidence;
- after the month shard writes its replay receipt, decision rows, coverage summary, row counts, and input hashes, the temporary month-cache data is deleted;
- retained replay evidence is lightweight manifest, receipt, coverage, hash, and decision-row evidence sufficient to prove what was replayed without keeping every transient downloaded input.

This keeps historical replay close to live execution while preventing the sealed replay contract from depending on whatever local source data happened to exist before the run.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_replay_dataset.py \
  --contract replays/promotion_replay_candidate_policy.json \
  --candidate-fold-id fold_2016-01_2016-06 \
  --training-target-ref AAPL \
  --tradable-universe-ref /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/tradable_universe.json \
  --output-root /root/projects/trading-storage/storage/05_replay_datasets \
  --data-root /root/projects/trading-storage/storage/01_source_data
```

The generated acquisition plan records feed parameters, target refs, asset classes, instrument types, and target output roots. Trading Economics rows use `use_authenticated_cookies=false`; the completed historical TE pass is a one-time replay seed and does not depend on an ongoing subscription. Historical provider calls require a separate one-shot replay acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed replay artifact.

## Frozen Snapshot

Replay data acquisition, event evidence collection, and source normalization are dataset construction phases for the explicit model fold, tradable universe, and replay window. Once the acquisition plan reaches accepted coverage and the replay is frozen, storage records a replay data snapshot for that scope.

All replay, fold settlement, promotion eligibility comparison, guardrail replay, and later regression checks for that fold and tradable-universe scope must reference that frozen snapshot. They must not re-download, re-sample, reinterpret, or rebuild replay data per model candidate. If the replay dataset is wrong or incomplete, the fix is a reviewed regenerated snapshot for the same scope or a new replay contract.

Replay evaluation uses `trading-execution`'s `execution_runtime_component_graph` under a historical clock and Replay adapters. The runner should feed the frozen point-in-time market, event, liquidity, and account-context inputs through the same task-level components used for live/shadow decision making. It must not use the model training pipeline, a training feature-generation route, or a separate evaluation-owned decision graph as the replay execution path. Layer 10 is reached only through the Failure Explanation Component after observed model or trade failure.

ThetaData option-chain snapshots remain replay-triggered. During historical realtime replay, a model buy or option-expression decision creates the point-in-time option snapshot request; selected-contract tracking expands from the concrete expiration/right/strike result. This keeps replay close to live behavior while preserving one frozen underlying/event/liquidity data substrate.

To freeze a prepared replay dataset after accepted coverage:

```bash
PYTHONPATH=src python3 scripts/evaluation/freeze_replay_dataset.py \
  --dataset-root /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy
```

The freeze command requires explicit `tradable_target_refs`, rejects missing acquisition count, and rejects target-dependent feed rows without `target_ref`. Deferred Alpaca rows are accepted only as a gated acquisition boundary for the explicit fold and tradable-universe scope.

To smoke-test that evaluation can call the execution-owned Replay route:

```bash
PYTHONPATH=src python3 scripts/evaluation/run_replay_runtime_dry_run.py \
  --account-sleeve-id crypto_spot_account \
  --target-ref SOL \
  --output-path /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/replay_runtime_dry_run_receipt.json
```

This smoke test is not a full fold replay. It proves the side-effect-free execution component graph call path and writes a receipt.

To plan or execute bounded one-shot acquisitions from the generated plan:

```bash
PYTHONPATH=src python3 scripts/evaluation/run_replay_acquisition.py \
  --dataset-root /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy \
  --source-id gdelt_news \
  --limit 10
```

Add `--execute` only when live provider acquisition should run. The runner writes one-shot task payloads and progress logs under the replay dataset root and still does not create manager request rows.
