# Architecture

## Modules

```text
src/trading_evaluation/benchmark.py           Benchmark contract parsing and validation.
src/trading_evaluation/benchmark_dataset.py   Benchmark dataset preparation manifests and one-shot acquisition planning.
src/trading_evaluation/settlement.py          Fold settlement metric assembly and validation.
src/trading_evaluation/promotion.py           Promotion eligibility and readiness validation.
scripts/evaluation/                          Thin executable wrappers over src.
tests/                                       Fixture-safe unit and CLI tests.
```

Future implementation slices may add:

- SQL migrations or SQL DDL owned by the accepted evaluation storage boundary.

## Flow

```text
BenchmarkContract
  -> BenchmarkValidation
  -> FoldSettlementRun
  -> FoldSettlementMetric[]
  -> PromotionEligibilityDecision
  -> PromotionReadinessRecord
  -> ExecutionShadowCycleSelection
```

The implemented scaffold validates benchmark contracts, prepares storage-side benchmark dataset manifests, builds fold settlement metrics from replay decision rows, and can build promotion readiness records from eligible evaluation decisions. Settlement covers return, baseline excess, drawdown, turnover proxy, hit-rate, payoff, AUROC, Brier score, and PCA/PCoA structure evidence when replay rows contain usable feature columns. Dataset preparation writes local storage runtime artifacts and one-shot acquisition requirements, but it does not use manager task/request rows, call providers unless explicitly executed through the gated one-shot acquisition runner, mutate SQL, freeze benchmark contracts, train models, switch active model configs, execute brokers, construct orders, or mutate accounts.

Benchmark data construction is separate from benchmark replay. Construction is a one-time storage-owned acquisition and normalization phase that produces the frozen reusable benchmark data snapshot. Replay and settlement then run candidates through the realtime execution decision path under a historical clock, reusing that same snapshot for every candidate and baseline. The benchmark path must not route through model training or rebuild point-in-time data differently per candidate.
