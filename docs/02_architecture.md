# Architecture

## Modules

```text
src/trading_evaluation/benchmark.py   Benchmark contract parsing and validation.
scripts/evaluation/                   Thin executable wrappers over src.
tests/                                Fixture-safe unit and CLI tests.
```

Future implementation slices may add:

- `src/trading_evaluation/settlement.py` for fold settlement metric assembly.
- `src/trading_evaluation/promotion.py` for promotion eligibility policies.
- SQL migrations or SQL DDL owned by the accepted evaluation storage boundary.

## Flow

```text
BenchmarkContract
  -> BenchmarkValidation
  -> FoldSettlementRun
  -> FoldSettlementMetric[]
  -> PromotionEligibilityDecision
```

The first implemented slice validates benchmark contracts only. It does not compute performance, query providers, mutate SQL, write storage artifacts, or activate models.

