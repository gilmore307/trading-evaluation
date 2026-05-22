# Tasks

## Active Tasks

- Extend Replay execution from the completed crypto fixed sleeve into full point-in-time candidate-policy Replay, including equity/options candidate materialization and candidate-dependent Alpaca rows.
- Review the completed crypto fixed-sleeve settlement result before using it as strategy evidence; it is `review_required` because AUROC did not meet the minimum gate.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- `gdelt_news`: complete, 60/60 monthly replay source artifacts available.
- `okx_crypto_market_data`: complete, 180/180 fixed crypto monthly artifacts available for `BTC-USDT`, `ETH-USDT`, and `SOL-USDT`.
- `trading_economics_calendar_web`: complete, 60/60 monthly artifacts available.
- `alpaca_bars`, `alpaca_liquidity`, and `alpaca_news`: intentionally deferred until point-in-time candidate symbols materialize during replay.

## Current State

- The replay contract validator and CLI enforce the accepted candidate-policy replay contract.
- Replay dataset manifests contain the replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot and does not use manager task/request rows.
- `evaluation_replay_runtime_dry_run` is a thin evaluation-side harness that calls `trading-execution` runtime builders directly.
- The candidate-policy Replay dataset is frozen for complete fixed crypto, GDELT, and Trading Economics monthly source artifacts; Alpaca source rows are intentionally deferred until candidate symbols materialize during Replay. Freeze receipt: `/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/replay_freeze_receipt.json`.
- Crypto fixed-sleeve Replay execution writes `5475` decision rows over `1826` market dates for `BTC`, `ETH`, and `SOL`, with no provider calls, broker calls, broker/account mutation, model training, or active config write.
- Crypto fixed-sleeve fold settlement `settlement_ad1cbf4f039eeb76` is `review_required` with gate failure `auroc_below_minimum`; do not promote from this evidence.
