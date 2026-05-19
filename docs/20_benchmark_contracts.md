# Benchmark Contracts

## Primary Benchmark Requirements

The primary benchmark must be selected once and then frozen.

Required properties:

- one benchmark contract with one or more frozen target/window components.
- fixed component weights for composite scoring.
- component asset class and theme bucket metadata.
- enough length to reduce accident and one-off event bias.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- deliberate coverage of then-hot thematic single-name winners, including names outside the selected ETF universe when target-context review exists.
- a small crypto sleeve because crypto is a future primary execution focus.
- no same-target window overlap with training-used folds.
- any fold for a benchmark target that intersects a benchmark component window must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.
- reviewed target-context refs for single-name equity and crypto components so non-ETF targets still use the accepted target/proxy mapping route.

Suggested composition:

- 60-75% equity single-name and ETF components.
- 15-25% then-hot thematic single-name components from storage, optical modules, rare earth, nuclear, data center, AI, or similar period-specific leadership themes.
- 5-15% crypto spot components.
- No single target, year, theme bucket, or market state should dominate the panel.

Do not concatenate component histories into one opaque series for judgment. Each component should produce its own metrics, guardrails, and regime slices; the composite is a fixed-weight aggregate over those component results.

## Guardrails

Guardrail benchmarks may catch overfit or pathological candidates. They should not replace the primary benchmark leaderboard unless a new benchmark contract is explicitly accepted.

## Current Selection Status

The first primary benchmark panel is not selected yet. Do not fabricate it from the current training target. Selection requires a reviewed market-coverage rationale and target/window exclusion proof for every component.
