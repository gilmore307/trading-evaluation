# Tasks

## Active Tasks

- Complete the remaining Layer 1/2 base-context coverage for the fold-bound replay dataset, then run replay through the execution-owned runtime component graph.
- Materialize true option-contract replay inputs for the equity/options account path. Replay may use direct-underlying fallback only as explicit missing option-surface evidence, not as proof that listed options were traded.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- Replay coverage is evaluated against explicit `candidate_fold_id`, `base_context_ref`, Layer 1/2 base-context refs, and fold scope.
- Layer 1/2 base-context source data is canonical historical source data shared with training and is retained after replay.
- Candidate equity, option, liquidity, and symbol-news data is not preexpanded. It is acquired on demand when the replayed execution components admit a sector, target, or option-expression point.
- Historical provider acquisition for on-demand replay data is gated and month-scoped. Temporary month-cache data is deleted after the shard writes replay receipts, decision rows, coverage summaries, row counts, and input hashes.

## Current State

- The replay contract validator and CLI support fold-bound candidate-policy replay windows with explicit `candidate_fold_id` and `base_context_ref`.
- Replay dataset manifests contain the replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot, gated, and does not use manager task/request rows.
- `evaluation_replay_runtime_dry_run` is a thin evaluation-side harness that calls `trading-execution` runtime builders directly.
- Replay execution unit is the `trading-execution` runtime component graph. Models are component input evidence, not the replay executor.
- Manager replay dispatch blocks only when replay dataset fold identity does not match the completed training fold.
- Manager evaluation blocks only when replay receipt fold identity does not match the completed training fold.
- The previous fixed crypto/ETF replay evidence is not valid because it was not produced from the fold-bound base-context replay contract and did not run through the accepted execution component path.
