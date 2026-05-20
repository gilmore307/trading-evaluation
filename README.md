# trading-evaluation

`trading-evaluation` is the independent benchmark, fold-settlement, and promotion-readiness repository for the trading system.

It owns frozen benchmark contracts, benchmark exclusion proof, fold settlement, model-performance comparison, promotion eligibility decisions, and promotion readiness records. It is the system's offline evaluation referee: it judges model candidates against accepted evidence and may admit them to execution shadow review, but it does not train models, switch active model configs, execute trades, mutate accounts, run provider acquisition, or own durable storage layout.

## Top-Level Structure

```text
docs/        Repository scope, architecture, contracts, tasks, decisions, and evaluation modules.
benchmarks/  Reviewable benchmark contract candidates before freeze.
scripts/     Executable evaluation and validation entrypoints.
src/         Importable benchmark, settlement, and promotion-eligibility helpers.
tests/       First-party tests.
```

`src/` owns reusable evaluation logic. `scripts/` may import `src/`; `src/` must not import `scripts/`.

## Docs Spine

```text
docs/
  00_scope.md
  01_context.md
  02_architecture.md
  03_contracts.md
  04_task.md
  05_decision.md
  06_memory.md
  20_benchmark_contracts.md
  22_benchmark_dataset_preparation.md
  30_fold_settlement.md
  40_promotion_eligibility.md
  50_promotion_readiness.md
```

## Current Route

```text
frozen benchmark contract
  -> two-year candidate-policy replay holdout proof
  -> benchmark dataset preparation manifest
  -> fold settlement run
  -> settlement metric rows/report refs
  -> fixed-rubric promotion reviewer advisory
  -> promotion eligibility decision
  -> promotion readiness record
  -> execution shadow cycle selection
```

The promotion benchmark is a frozen two-year historical-clock replay. The candidate model must generate candidates from the accepted candidate policy, rank/select targets itself, and run through the realtime decision route against a frozen snapshot and cost model. Guardrail benchmarks may exist for overfit detection, but they do not replace the primary replay leaderboard unless a new benchmark contract is explicitly accepted.

Agent review, when used, must follow the workspace skill `skills/openclaw/promotion-evaluation-review`. The reviewer produces advisory structured evidence only; deterministic evaluation code validates eligibility and writes promotion readiness records.

## Platform Boundaries

- `trading-model` owns training, model generation, and raw model outputs.
- `trading-evaluation` owns independent benchmark evaluation, fold settlement, promotion eligibility, and promotion readiness records.
- `trading-execution` owns live/shadow runtime model selection and active model switching after a market-hours shadow cycle.
- `trading-manager` owns scheduling and control-plane state, not model-quality judgment or activation.
- `trading-storage` owns durable settlement reports, references, backup, archive, restore, and lifecycle.
- `trading-execution` owns broker/exchange execution and account mutation.

Shared names, fields, statuses, scripts, and contract ids discovered here must be registered through `trading-manager` before other repositories depend on them.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src scripts
PYTHONPATH=src python3 scripts/evaluation/validate_benchmark_contract.py --input tests/fixtures/benchmark_contract_valid.json
PYTHONPATH=src python3 scripts/evaluation/build_promotion_readiness_record.py --promotion-eligibility-json tests/fixtures/promotion_eligibility_eligible.json --candidate-model-ref storage://models/market_regime/new --candidate-config-ref storage://configs/market_regime/new --rollback-ref storage://models/market_regime/old
```
