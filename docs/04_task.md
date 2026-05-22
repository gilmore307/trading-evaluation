# Tasks

## Active Tasks

- Freeze the first candidate-policy replay for the canonical `2021-01-01` to `2026-01-01` end-exclusive window after the three Trading Economics visible-page browser-fallback gaps are filled. Replay windows must remain excluded from training folds.
- Run fold settlement metric assembly after replay produces decision rows; `scripts/evaluation/build_fold_settlement_run.py` now emits AUROC, return/drawdown/cost/hit-rate, and PCA/PCoA-style structure diagnostics for agent-assisted promotion review.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- `gdelt_news`: complete, 60/60 monthly replay source artifacts available.
- `okx_crypto_market_data`: complete, 180/180 fixed crypto monthly artifacts available for `BTC-USDT`, `ETH-USDT`, and `SOL-USDT`.
- `trading_economics_calendar_web`: 57/60 monthly artifacts available; `2022-07`, `2024-06`, and `2025-09` currently need the reviewed browser UI fallback because the bounded HTTP/cookie visible-page route returned HTTP 405 after retry.
- `alpaca_bars`, `alpaca_liquidity`, and `alpaca_news`: intentionally deferred until point-in-time candidate symbols materialize during replay.

## Recently Accepted

- Created `trading-evaluation` as the independent replay, fold-settlement, promotion-eligibility, and promotion-readiness repository.
- Implemented the first fixture-safe replay contract validator and CLI.
- Prepared the replay dataset manifest route: replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot and does not use manager task/request rows.
- Added `evaluation_replay_runtime_dry_run`, a thin evaluation-side Replay harness that calls `trading-execution` runtime builders directly instead of duplicating trading decisions.
- Prepared the candidate-policy Replay dataset against the current execution runtime component graph, expanded fixed crypto acquisition for the separate crypto account candidate pool, and added bounded replay acquisition retry support for Trading Economics visible pages.
