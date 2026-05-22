# Tasks

## Active Tasks

- Define and freeze the first candidate-policy replay for the canonical `2021-01-01` to `2026-01-01` end-exclusive window after dataset preparation coverage is inspected. Replay windows must remain excluded from training folds.
- Run fold settlement metric assembly after replay produces decision rows; `scripts/evaluation/build_fold_settlement_run.py` now emits AUROC, return/drawdown/cost/hit-rate, and PCA/PCoA-style structure diagnostics for agent-assisted promotion review.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Recently Accepted

- Created `trading-evaluation` as the independent replay, fold-settlement, promotion-eligibility, and promotion-readiness repository.
- Implemented the first fixture-safe replay contract validator and CLI.
- Prepared the replay dataset manifest route: replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot and does not use manager task/request rows.
- Added `evaluation_replay_runtime_dry_run`, a thin evaluation-side Replay harness that calls `trading-execution` runtime builders directly instead of duplicating trading decisions.
