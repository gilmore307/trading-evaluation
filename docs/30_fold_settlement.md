# Fold Settlement

Fold settlement is the comprehensive post-fold evaluation step.

It should run after a fold has completed Layer 1 through Layer 10 model evaluation and before promotion eligibility is accepted. Single-layer fold evaluation can be stored as diagnostic evidence, but promotion judgment evaluates one pinned Layer 1-10 version bundle. The bundle is accepted or rejected as a whole; no single layer or partial substack is promotion-ready by itself.

## Current Metric Contract

- return and excess return.
- max drawdown.
- turnover proxy and cost drag.
- hit rate and payoff ratio.
- AUROC and Brier score when replay rows contain labels and scores.
- PCA/PCoA-style feature structure diagnostics when numeric feature columns are present.
- comparison against frozen baselines.

Additional families such as Sharpe/Sortino-style risk-adjusted measures, exposure time, abstention quality, event-risk intervention effect, and richer calibration slices belong in later settlement expansions once replay rows expose the required fields.

## Storage Boundary

Detailed settlement reports and chart-ready summaries are durable artifacts and should be stored through `trading-storage` contracts. This repository owns metric semantics and validation.

## Implementation

`src/trading_evaluation/settlement.py` and `scripts/evaluation/build_fold_settlement_run.py` assemble a `fold_settlement_run` from replay decision rows. The settlement helper computes return, excess return, max drawdown, turnover proxy, hit rate, payoff ratio, AUROC, Brier score, and PCA/PCoA-style structure diagnostics when numeric feature columns are present.

Rows with a selected option contract and `option_contract_path_status =
missing` are retained as coverage diagnostics, but they are excluded from
filled-trade turnover and label/score pairs. They must not create synthetic
zero-return option losses.

The settlement run always sets `agent_review_required=true` with `agent_review_scope=promotion-evaluation-review`. Deterministic gates can mark the run `passed` or `review_required`, but they do not promote a model or write execution active pointers by themselves.

Current crypto fixed-sleeve settlement evidence is `review_required`, not
promotion-ready. It produced positive excess return against the cash baseline,
but failed the AUROC gate, so it needs review or candidate-policy/model
improvement before it can support promotion.
