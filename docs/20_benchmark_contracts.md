# Benchmark Contracts

## Promotion Benchmark Requirements

The promotion benchmark must be selected once and then frozen. For Layer 3 and later target-selection models, the benchmark is a two-year historical-clock replay. It freezes the candidate-generation policy and historical replay substrate, not a hand-picked list of final trade targets.

Required properties:

- one benchmark contract with `benchmark_mode = candidate_policy_replay`.
- one continuous replay window covering at least two calendar years and at least 504 expected trading days.
- a frozen candidate-universe policy, historical data snapshot, cost model, baseline ladder, selection metrics, and guardrails.
- candidate policy inputs covering current Layer 2 selected/watch sectors, reviewed sector constituents or proxies, current market-wide hot/liquid names, quality filters, and control candidates when contrast is required.
- the model must generate candidates, rank/select targets, and run through the realtime decision route under a historical clock.
- no `target_symbol`, fixed final target list, or `benchmark_components`.
- metrics must evaluate realized replay performance after cost, risk, drawdown, turnover, selection quality, and guardrails.
- metadata for candidate source, market state, Layer 2 sector source, event state, data availability, and model decision provenance.
- explicit sector coverage metadata, including consumer and entertainment/media coverage.
- enough length to reduce accident and one-off event bias.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- explicit event coverage metadata for earnings-crossing windows, policy/macro shocks, liquidity or squeeze events, product-cycle repricing, and crypto-cycle events.
- deliberate point-in-time admission of then-hot thematic single-name candidates through the candidate policy, including names outside the selected ETF universe when target-context review exists.
- a small crypto sleeve because crypto is a future primary execution focus.
- a small controlled stress sleeve for critical data-edge cases such as crypto missing quote/order-book context, sparse bars, missing Layer 2 context, or partial event coverage.
- no leakage from the frozen two-year replay window into training-used folds.
- any fold that intersects the sealed promotion replay window must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.
- benchmark acquisition and event/source normalization are one-time construction phases that produce a frozen reusable data snapshot for the contract.
- all benchmark replay, settlement, promotion eligibility, guardrail, and regression checks must reuse that frozen data snapshot instead of rebuilding data per model candidate.
- benchmark evaluation must run through the realtime execution decision path under a historical clock, not through the model training pipeline.
- reviewed target-context refs available to the candidate policy so non-ETF targets still use the accepted target/proxy mapping route.

Required replay behavior:

- the candidate model gets the full two-year replay period and must operate according to the same model route intended for live use.
- Layer 2 produces sector context point-in-time; Layer 3 generates/ranks the candidate set; downstream layers decide whether and how to trade.
- the benchmark judges final realized replay performance and guardrail behavior, not isolated hand-picked episodes.
- replay output must preserve enough per-decision evidence to audit why targets were selected, watched, blocked, traded, or skipped.

Suggested replay coverage:

- two recent years with completed data and enough different market states to avoid a one-regime benchmark.
- consumer discretionary, consumer staples, entertainment/media, technology/AI, energy, healthcare, financials, broad-market, and crypto context should be reachable through the candidate policy when point-in-time conditions support them.
- event-heavy periods, earnings periods, liquidity stress, strong trend, drawdown, rotation, and high-volatility states should appear naturally in the replay window.

Do not concatenate replay histories into one opaque series for judgment. Each month, market regime, candidate source, selected/top-N group, watch/blocked group, trade/skip reason, guardrail, and risk slice should produce its own metrics; the final decision uses the full two-year replay result plus slice diagnostics.

## Guardrails

Guardrail benchmarks may catch overfit or pathological candidates. They should not replace the promotion benchmark leaderboard unless a new benchmark contract is explicitly accepted.

## Current Selection Status

The first promotion benchmark is not frozen yet. The prior fixed target/window artifact was deleted because it preselected final targets and is no longer applicable.

Do not use fixed target/window panels for training, tuning, prompt iteration, model selection, or promotion. Full promotion judgment requires an accepted two-year candidate-policy replay benchmark.
