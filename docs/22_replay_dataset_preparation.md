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
- candidate fold id: explicit, for example `fold_2016-01_2016-06`
- base context artifact: explicit Layer 1/2 base-context used to validate replay substrate coverage
- local coverage scan root: `trading-storage/storage/01_source_data`
- runtime output root: `trading-storage/storage/05_replay_datasets`

## Feed Requirements

Candidate-policy replay prepares one-shot acquisition requirements for the full replay window:

- `01_feed_alpaca_bars` for Layer 1/2 base-context refs, reused from canonical monthly backfill
- `05_feed_gdelt_news` for broad market, sector, theme, and symbol event evidence
- `07_feed_trading_economics_calendar_web` for high-importance U.S. macro event evidence through logged-out visible-page custom-date requests
- `04_feed_okx_crypto_market_data` only when the base context includes crypto context refs

Replay predeclares only the Layer 1/2 base-context refs through `base_context_ref`, expanded into `pre_replay_target_refs` in the dataset manifest. Replay must not infer its candidate set by scanning already materialized local bar directories. Candidate equities, symbol-scoped liquidity/news, and option-chain snapshots are discovered during execution-component replay after C01 admits sectors/targets and downstream components create buy or option-expression points. Selected-contract feeds (`10_feed_thetadata_option_primary_tracking` and `11_feed_thetadata_option_event_timeline`) expand only after those snapshots produce concrete expiration/right/strike selections.

## Replay Acquisition Boundary

Replay acquisition is bounded by the historical replay clock, candidate policy, execution component graph, and monthly shard budget:

- preflight may query or estimate source coverage, request counts, row counts, and storage footprint before provider execution;
- Layer 1/2 base-context source data lives in canonical long-lived monthly backfill source roots and is retained after replay;
- provider execution may temporarily materialize only the month and candidate set admitted by C01-C07 during the replay shard;
- temporary on-demand month-cache data lives under the replay dataset/run boundary, not under canonical long-lived monthly backfill source roots;
- raw provider payloads are not persisted unless a source contract explicitly requires raw evidence;
- after the month shard writes its replay receipt, decision rows, coverage summary, row counts, and input hashes, the temporary month-cache data is deleted;
- retained replay evidence is lightweight manifest, receipt, coverage, hash, and decision-row evidence sufficient to prove what was replayed without keeping every transient downloaded input.

This keeps historical replay close to live execution while preserving the training-shared base data and preventing the sealed replay contract from depending on ad hoc local candidate data.

## Command

```bash
PYTHONPATH=src python3 scripts/evaluation/prepare_replay_dataset.py \
  --contract replays/promotion_replay_candidate_policy.json \
  --candidate-fold-id fold_2016-01_2016-06 \
  --base-context-ref /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/base_context.json \
  --output-root /root/projects/trading-storage/storage/05_replay_datasets \
  --data-root /root/projects/trading-storage/storage/01_source_data
```

The generated acquisition plan records feed parameters, base refs, asset classes, instrument types, and output roots. Trading Economics rows use `use_authenticated_cookies=false`; the completed historical TE pass is a one-time replay seed and does not depend on an ongoing subscription. Historical provider calls for missing base rows or on-demand candidate rows require a separate one-shot replay acquisition gate, but they do not need manager task rows or reusable task keys because this dataset is a sealed replay artifact.

## Frozen Snapshot

Replay base data acquisition, event evidence collection, and source normalization are dataset construction phases for the explicit model fold and replay window. Once the base acquisition plan reaches accepted coverage and the replay is frozen, storage records a replay data snapshot for that scope.

All replay, fold settlement, promotion eligibility comparison, guardrail replay, and later regression checks for that fold and base-context scope must reference that frozen snapshot. They must not re-download, re-sample, reinterpret, or rebuild base replay data per model candidate. If the replay dataset is wrong or incomplete, the fix is a reviewed regenerated snapshot for the same scope or a new replay contract.

Replay evaluation uses `trading-execution`'s `execution_runtime_component_graph` under a historical clock and Replay adapters. The runner feeds frozen point-in-time base context plus on-demand candidate evidence through the same task-level components used for live decision making. Models are inputs to those components; the execution unit is C01-C07, not a model layer. Replay must not use the model training pipeline, a training feature-generation route, or a separate evaluation-owned decision graph as the replay execution path. Layer 10 is reached only through the Failure Explanation Component after observed model or trade failure.

Replay component outputs use the same artifact contracts as live execution:
`execution_intake_snapshot`, `entry_decision`,
`position_lifecycle_decision`, `option_reexpression_decision`,
`execution_order_intent`, `execution_gate_result`, and
`failure_explanation_packet`. Replay-specific files in this repository are
receipts, progress records, coverage summaries, settlement views, and promotion
evidence. They are not replacements for execution-owned component artifacts.

ThetaData option-chain snapshots remain replay-triggered. During historical realtime replay, a component buy or option-expression decision creates the point-in-time option snapshot request; selected-contract tracking expands from the concrete expiration/right/strike result. This keeps replay close to live behavior while preserving one frozen base data substrate.

To freeze a prepared replay dataset after accepted coverage:

```bash
PYTHONPATH=src python3 scripts/evaluation/freeze_replay_dataset.py \
  --dataset-root /root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy
```

The freeze command requires explicit `pre_replay_target_refs` and rejects missing base acquisition count. On-demand candidate rows are not part of the base freeze; they are gated by replay execution month shards.

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
