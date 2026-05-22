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

Future implementation slices may add:

- SQL migrations or SQL DDL owned by the accepted evaluation storage boundary.

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

The implemented scaffold validates replay contracts, prepares storage-side replay dataset manifests, runs the frozen crypto sleeve through execution-owned Replay components, builds fold settlement metrics from replay decision rows, and can build promotion readiness records from eligible evaluation decisions. Settlement covers return, baseline excess, drawdown, turnover proxy, hit-rate, payoff, AUROC, Brier score, and PCA/PCoA structure evidence when replay rows contain usable feature columns. Dataset preparation writes local storage runtime artifacts and one-shot acquisition requirements, but it does not use manager task/request rows, call providers unless explicitly executed through the gated one-shot acquisition runner, mutate SQL, freeze replay contracts, train models, switch active model configs, execute brokers, construct orders, or mutate accounts.

Replay data construction is separate from replay execution. Construction is a one-time storage-owned acquisition and normalization phase that produces the frozen reusable replay data snapshot. Replay then calls `trading-execution`'s `execution_runtime_component_graph` under Replay adapters, reusing that same snapshot for every candidate and baseline. `trading-evaluation` owns orchestration, settlement, metrics, promotion eligibility, and promotion readiness; it does not duplicate trading decisions that belong to execution components. The replay path must not route through model training or rebuild point-in-time data differently per candidate.
