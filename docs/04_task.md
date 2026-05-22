# Tasks

## Active Tasks

- Extend Replay execution from the completed crypto fixed sleeve into full point-in-time candidate-policy Replay, including equity/options candidate materialization and candidate-dependent Alpaca rows.
- Review the completed crypto fixed-sleeve settlement result before using it as strategy evidence; it is `review_required` because AUROC did not meet the minimum gate.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- `gdelt_news`: complete, 60/60 monthly replay source artifacts available.
- `okx_crypto_market_data`: complete, 180/180 fixed crypto monthly artifacts available for `BTC-USDT`, `ETH-USDT`, and `SOL-USDT`.
- `trading_economics_calendar_web`: complete, 60/60 monthly artifacts available after bounded retry of the Custom date visible-page route.
- `alpaca_bars`, `alpaca_liquidity`, and `alpaca_news`: intentionally deferred until point-in-time candidate symbols materialize during replay.

## Recently Accepted

- Created `trading-evaluation` as the independent replay, fold-settlement, promotion-eligibility, and promotion-readiness repository.
- Implemented the first fixture-safe replay contract validator and CLI.
- Prepared the replay dataset manifest route: replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot and does not use manager task/request rows.
- Added `evaluation_replay_runtime_dry_run`, a thin evaluation-side Replay harness that calls `trading-execution` runtime builders directly instead of duplicating trading decisions.
- Prepared the candidate-policy Replay dataset against the current execution runtime component graph, expanded fixed crypto acquisition for the separate crypto account candidate pool, and added bounded replay acquisition retry support for Trading Economics visible pages.
- Completed the one-shot Replay source acquisition pass for fixed crypto, GDELT, and Trading Economics monthly source artifacts; remaining Alpaca source rows are intentionally deferred until candidate symbols materialize during Replay.
- Froze the first candidate-policy Replay dataset after correcting OKX artifact paths to `instrument/month` granularity and validating that all non-deferred source acquisitions have distinct succeeded receipts. Freeze receipt: `/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/replay_freeze_receipt.json`.
- Ran crypto fixed-sleeve Replay execution through `trading-execution` Replay components: `5475` decision rows over `1826` market dates for `BTC`, `ETH`, and `SOL`, with no provider calls, broker calls, broker/account mutation, model training, or active config write.
- Built fold settlement for the crypto fixed-sleeve Replay. Settlement `settlement_ad1cbf4f039eeb76` is `review_required` with gate failure `auroc_below_minimum`; do not promote from this evidence.
