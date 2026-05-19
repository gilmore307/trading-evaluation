# Benchmark Contracts

## Primary Benchmark Requirements

The primary benchmark must be selected once and then frozen.

Required properties:

- one benchmark contract with one or more frozen target/window components.
- fixed component weights for composite scoring.
- enough length to reduce accident and one-off event bias.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- no same-target window overlap with training-used folds.
- any fold for a benchmark target that intersects a benchmark component window must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.

Do not concatenate component histories into one opaque series for judgment. Each component should produce its own metrics, guardrails, and regime slices; the composite is a fixed-weight aggregate over those component results.

## Guardrails

Guardrail benchmarks may catch overfit or pathological candidates. They should not replace the primary benchmark leaderboard unless a new benchmark contract is explicitly accepted.

## Current Selection Status

The first primary benchmark panel is not selected yet. Do not fabricate it from the current training target. Selection requires a reviewed market-coverage rationale and target/window exclusion proof for every component.
