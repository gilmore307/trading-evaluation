# Tasks

## Active Tasks

- Materialize true option-contract replay inputs for the equity/options account path. Current candidate-policy Replay can trade materialized Alpaca equity bars through a direct-underlying fallback and marks missing option surface evidence explicitly.
- Review the completed candidate-policy settlement result before using it as strategy evidence; it remains promotion-blocked by evaluation gates.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Current Replay Dataset Coverage

- `gdelt_news`: complete, 60/60 monthly replay source artifacts available.
- `okx_crypto_market_data`: complete, 180/180 fixed crypto monthly artifacts available for `BTC-USDT`, `ETH-USDT`, and `SOL-USDT`.
- `trading_economics_calendar_web`: complete, 60/60 monthly artifacts available.
- `alpaca_bars`: materialized during Replay from local monthly backfill for the eligible equity/ETF universe.
- `alpaca_liquidity` and `alpaca_news`: intentionally deferred until point-in-time candidate symbols need those feeds during replay.

## Current State

- The replay contract validator and CLI enforce the accepted candidate-policy replay contract.
- Replay dataset manifests contain the replay-window manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Replay acquisition is one-shot and does not use manager task/request rows.
- `evaluation_replay_runtime_dry_run` is a thin evaluation-side harness that calls `trading-execution` runtime builders directly.
- The candidate-policy Replay dataset is frozen for complete fixed crypto, GDELT, and Trading Economics monthly source artifacts. Freeze receipt: `/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy/replay_freeze_receipt.json`.
- Candidate-policy Replay execution `model_group_replay_candidate_policy_equity_20260530T051209Z` writes `59032` decision rows over `1826` market dates for `44` Alpaca equity/ETF targets plus `BTC`, `ETH`, and `SOL`, with no provider calls, broker calls, broker/account mutation, model training, or active config write.
- Equity/options account rows currently use `direct_underlying_fallback` with `option_surface_status=optionable_chain_missing`; true stock-option contract replay remains blocked until option-expression acquisition materializes option surfaces/contracts.
- Candidate-policy fold settlement `model_group_evaluation_20260530T053633Z` is promotion-blocked; do not promote from this evidence.
