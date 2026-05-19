# Scope

## Purpose

`trading-evaluation` is the independent benchmark, fold-settlement, promotion-eligibility, and promotion-readiness repository for the trading system.

It exists to keep model-quality judgment separate from model training, manager orchestration, storage lifecycle, dashboard display, and execution.

## In Scope

- frozen primary benchmark contracts.
- benchmark panel component/window selection requirements.
- proof that benchmark target/window pairs are excluded from same-target training folds.
- fold settlement run contracts.
- settlement metric and report-reference contracts.
- baseline comparison policy.
- guardrail benchmark policy for overfit detection.
- promotion eligibility decisions derived from settlement evidence.
- promotion readiness records admitting candidates to execution shadow review.
- fixture-safe validation helpers for benchmark contracts.

## Out of Scope

- provider data acquisition.
- feature generation.
- model training or model output generation.
- control-plane scheduling, retries, or workflow ownership.
- broker orders, positions, fills, or account mutation.
- durable storage layout, backup, archive, restore, or deletion.
- dashboard visualization.
- global registry authority outside `trading-manager`.
- secrets or generated runtime artifacts committed to Git.

## Boundary Rules

- Evaluation may judge a candidate and publish promotion readiness records.
- Runtime activation and active model selection belong to `trading-execution`; evaluation must not switch active configs.
- The primary benchmark must be stable across folds; changing it requires a new accepted benchmark contract version, not silent replacement.
- A benchmark target may appear in training only outside its sealed benchmark windows. Same-target training folds that overlap a benchmark component window must be skipped or blocked.
- Detailed settlement artifacts belong under `trading-storage` contracts; this repository owns their semantic validation and summary metric meaning.
- Shared names must be registered in `trading-manager` before cross-repository use.
