# Benchmark Contracts

## Primary Benchmark Requirements

The primary benchmark must be selected once and then frozen.

Required properties:

- one target symbol.
- one start/end window.
- enough length to reduce accident and one-off event bias.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- no target overlap with training-used targets.
- no window leakage into training or candidate-building splits.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.

## Guardrails

Guardrail benchmarks may catch overfit or pathological candidates. They should not replace the primary benchmark leaderboard unless a new benchmark contract is explicitly accepted.

## Current Selection Status

The first primary benchmark target/window is not selected yet. Do not fabricate it from the current training target. Selection requires a reviewed market-coverage rationale and exclusion proof.

