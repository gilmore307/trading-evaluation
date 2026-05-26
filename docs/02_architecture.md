# Architecture

## Modules

```text
src/trading_evaluation/replay.py           Replay contract parsing and validation; current replay API.
src/trading_evaluation/replay_dataset.py   Replay dataset preparation manifests and one-shot acquisition planning; current replay API.
src/trading_evaluation/replay_execution.py Frozen-source Replay execution through trading-execution components.
src/trading_evaluation/settlement.py          Fold settlement metric assembly and validation.
src/trading_evaluation/promotion.py           Promotion eligibility and readiness validation.
scripts/evaluation/                          Thin executable wrappers over src.
tests/                                       Fixture-safe unit and CLI tests.
```

## Flow

```text
ReplayContract
  -> ReplayValidation
  -> ReplayDatasetPreparationManifest
  -> ReplayDatasetFreezeReceipt
  -> trading-execution execution_runtime_component_graph under Replay adapters
  -> ReplayExecutionRun / decision rows
  -> FoldSettlementRun
  -> FoldSettlementMetric[]
  -> PromotionEligibilityDecision
  -> PromotionReadinessRecord
  -> ExecutionShadowCycleSelection
```

The active route validates replay contracts, prepares storage-side replay dataset manifests, freezes accepted replay coverage, runs the frozen crypto sleeve through execution-owned Replay components, builds fold settlement metrics from replay decision rows, and builds promotion readiness records only from eligible evaluation decisions. Settlement covers return, baseline excess, drawdown, turnover proxy, hit-rate, payoff, AUROC, Brier score, and PCA/PCoA structure evidence when replay rows contain usable feature columns. Dataset preparation writes local storage runtime artifacts and one-shot acquisition requirements, but it does not use manager task/request rows, call providers unless explicitly executed through the gated one-shot acquisition runner, mutate SQL, train models, switch active model configs, execute brokers, construct orders, or mutate accounts.

Replay data construction is separate from replay execution. Construction is a one-time storage-owned acquisition and normalization phase that produces the frozen reusable replay data snapshot. Replay then calls `trading-execution`'s `execution_runtime_component_graph` under Replay adapters, reusing that same snapshot for every candidate and baseline. `trading-evaluation` owns orchestration, settlement, metrics, promotion eligibility, and promotion readiness; it does not duplicate trading decisions that belong to execution components. The replay path must not route through model training or rebuild point-in-time data differently per candidate.

## SQL Evidence Tables

Evaluation-owned evidence is SQL-backed under the `trading_evaluation` schema:

```text
trading_evaluation.replay_contract
trading_evaluation.replay_dataset_preparation
trading_evaluation.replay_dataset_freeze
trading_evaluation.replay_source_coverage
trading_evaluation.replay_execution_run
trading_evaluation.replay_decision
trading_evaluation.replay_progress
trading_evaluation.fold_settlement_run
trading_evaluation.fold_settlement_metric
trading_evaluation.promotion_eligibility_decision
trading_evaluation.promotion_readiness_record
trading_evaluation.promoted_model_parameter
```

Storage artifacts may hold detailed reports, large JSONL decision traces, or chart-ready files, but the fold/replay/promotion state needed for comparison, filtering, and lifecycle decisions belongs in these SQL tables.
