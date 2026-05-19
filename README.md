# trading-evaluation

`trading-evaluation` is the independent evaluation, promotion-eligibility, and model-activation repository for the trading system.

It owns frozen benchmark contracts, benchmark exclusion proof, fold settlement, model-performance comparison, promotion eligibility decisions, and model activation records. It is the system's evaluation referee and release authority for model configs: it judges model candidates against accepted evidence and may publish the active model config, but it does not train models, execute trades, mutate accounts, run provider acquisition, or own durable storage layout.

## Top-Level Structure

```text
docs/        Repository scope, architecture, contracts, tasks, decisions, and evaluation modules.
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
  30_fold_settlement.md
  40_promotion_eligibility.md
  50_activation.md
```

## Current Route

```text
frozen benchmark contract
  -> benchmark exclusion proof
  -> fold settlement run
  -> settlement metric rows/report refs
  -> fixed-rubric promotion reviewer advisory
  -> promotion eligibility decision
  -> model activation record / active model config
```

The primary benchmark is one fixed target and one fixed window so fold-to-fold results remain horizontally comparable. Guardrail benchmarks may exist for overfit detection, but they do not replace the primary leaderboard unless a new benchmark contract version is explicitly accepted.

Agent review, when used, must follow the workspace skill `skills/openclaw/promotion-evaluation-review`. The reviewer produces advisory structured evidence only; deterministic evaluation code validates eligibility and writes activation records.

## Platform Boundaries

- `trading-model` owns training, model generation, and raw model outputs.
- `trading-evaluation` owns independent benchmark evaluation, fold settlement, promotion eligibility, and model activation records.
- `trading-manager` owns scheduling and control-plane state, not model-quality judgment or activation.
- `trading-storage` owns durable settlement reports, references, backup, archive, restore, and lifecycle.
- `trading-execution` owns broker/exchange execution and account mutation.

Shared names, fields, statuses, scripts, and contract ids discovered here must be registered through `trading-manager` before other repositories depend on them.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src scripts
PYTHONPATH=src python3 scripts/evaluation/validate_benchmark_contract.py --input tests/fixtures/benchmark_contract_valid.json
PYTHONPATH=src python3 scripts/evaluation/build_model_activation_record.py --promotion-eligibility-json tests/fixtures/promotion_eligibility_eligible.json --activated-model-id market_regime_model --activated-config-ref storage://models/market_regime/new --active-model-config-ref storage://evaluation/active/market_regime_model --rollback-ref storage://models/market_regime/old --activation-scope shadow
```
