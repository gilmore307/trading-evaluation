# Tasks

## Active Tasks

- Regenerate the model-group replay dataset as an explicit fold-target snapshot for `AAPL` `fold_2016-01_2016-06`.
- Materialize true option-contract replay inputs for the equity/options account path. Replay may use direct-underlying fallback only as explicit missing option-surface evidence, not as proof that listed options were traded.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- Replay coverage is now evaluated against explicit `target_refs` and fold scope.
- Target-dependent Alpaca rows must carry `target_ref`, `asset_class`, and `instrument_type`.
- For `AAPL` fold replay, OKX crypto rows are not part of the dataset unless the explicit target refs include crypto targets.
- Historical provider acquisition is gated and month-scoped. Temporary month-cache data is deleted after the shard writes replay receipts, decision rows, coverage summaries, row counts, and input hashes.

## Current State

- The replay contract validator and CLI support fold-bound candidate-policy replay windows with explicit `candidate_fold_id` and `target_refs`.
- Replay dataset manifests contain the replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot, gated, and does not use manager task/request rows.
- `evaluation_replay_runtime_dry_run` is a thin evaluation-side harness that calls `trading-execution` runtime builders directly.
- Manager replay dispatch blocks any frozen dataset whose `target_refs` do not include the completed training target.
- Manager evaluation blocks any replay receipt whose `target_refs` do not include the completed training target.
- The previous fixed crypto/ETF replay evidence is not valid for `AAPL` fold replay and must not be used as promotion evidence.
