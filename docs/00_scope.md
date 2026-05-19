# Scope

## Purpose

`trading-evaluation` is the independent benchmark, fold-settlement, promotion-eligibility, and model-activation repository for the trading system.

It exists to keep model-quality judgment separate from model training, manager orchestration, storage lifecycle, dashboard display, and execution.

## In Scope

- frozen primary benchmark contracts.
- benchmark target/window selection requirements.
- proof that benchmark targets and windows are excluded from training.
- fold settlement run contracts.
- settlement metric and report-reference contracts.
- baseline comparison policy.
- guardrail benchmark policy for overfit detection.
- promotion eligibility decisions derived from settlement evidence.
- model activation records and active model config contracts.
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

- Evaluation may judge a candidate and publish model activation records.
- Model activation is a config release action; it must not execute broker/order/account mutation.
- The primary benchmark must be stable across folds; changing it requires a new accepted benchmark contract version, not silent replacement.
- A benchmark target must not be a training target, and benchmark windows must be excluded from training/evaluation splits used to build the candidate.
- Detailed settlement artifacts belong under `trading-storage` contracts; this repository owns their semantic validation and summary metric meaning.
- Shared names must be registered in `trading-manager` before cross-repository use.
