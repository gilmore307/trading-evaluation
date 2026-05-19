# Fold Settlement

Fold settlement is the comprehensive post-fold evaluation step.

It should run after a fold has completed all model-worker stages and before promotion eligibility is accepted.

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

