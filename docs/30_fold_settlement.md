# Fold Settlement

Fold settlement is the comprehensive post-fold evaluation step.

It should run after a fold has completed Layer 1 through Layer 10 model evaluation and before promotion eligibility is accepted. Single-layer fold evaluation can be stored as diagnostic evidence, but promotion judgment evaluates one pinned Layer 1-10 version bundle. The bundle is accepted or rejected as a whole; no single layer or partial substack is promotion-ready by itself.

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
