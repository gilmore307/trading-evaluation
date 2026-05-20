# Fold Settlement

Fold settlement is the comprehensive post-fold evaluation step.

It should run after a fold has completed Layer 1 through Layer 9 model evaluation and before promotion eligibility is accepted. Single-layer fold evaluation can be stored as diagnostic evidence, but it is not promotion-ready until the full stack for that fold is complete.

## Required Metric Families

- return and excess return.
- drawdown and tail loss.
- Sharpe/Sortino-style risk-adjusted measures.
- turnover, trade count, exposure time, and cost drag.
- hit rate and payoff ratio.
- abstention quality.
- event-risk intervention effect.
- calibration of confidence and action strength.
- comparison against frozen baselines.

## Storage Boundary

Detailed settlement reports and chart-ready summaries are durable artifacts and should be stored through `trading-storage` contracts. This repository owns metric semantics and validation.
