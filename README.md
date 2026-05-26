# trading-evaluation

`trading-evaluation` is the independent replay, fold-settlement, promotion-eligibility, and promotion-readiness repository for the trading system.

It owns frozen replay contracts, replay-window training-exclusion proof, fold settlement, model-performance comparison, promotion eligibility decisions, and promotion readiness records. It is the system's offline evaluation referee: it judges model candidates against accepted evidence and may admit them to execution shadow review, but it does not train models, switch active model configs, execute trades, mutate accounts, run provider acquisition, or own durable storage layout.

## Top-Level Structure

```text
docs/     Repository scope, architecture, contracts, tasks, decisions, and evaluation modules.
replays/  Reviewable promotion replay contracts.
scripts/     Executable evaluation and validation entrypoints.
src/         Importable replay, settlement, and promotion-eligibility helpers.
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
  20_replay_contracts.md
  22_replay_dataset_preparation.md
  30_fold_settlement.md
  40_promotion_eligibility.md
  50_promotion_readiness.md
```

## Current Route

```text
frozen replay contract
  -> candidate-policy replay holdout proof
  -> replay dataset preparation manifest
  -> execution runtime component graph under Replay adapters
  -> frozen replay execution decision rows
  -> fold settlement run
  -> settlement metric rows/report refs
  -> fixed-rubric promotion reviewer advisory
  -> promotion eligibility decision
  -> promotion readiness record
  -> execution shadow cycle selection
```

The promotion replay is a frozen historical-clock candidate-policy replay over the canonical fixed window `2021-01-01` through `2026-01-01` end-exclusive, covering the full 2021-2025 calendar years and 1255 expected NYSE trading days. The candidate model generates candidates from the accepted candidate policy, ranks and selects targets, and runs through `trading-execution`'s `execution_runtime_component_graph` with Replay adapters against the frozen snapshot and cost model. The active execution runner covers the fixed crypto sleeve and writes settlement-ready decision rows; full equity/options candidate materialization remains active work. Guardrail replays may exist for overfit detection, but they do not replace the primary replay leaderboard unless a new replay contract is explicitly accepted.

Replay is not shadow. Replay uses fixed historical data to decide whether a
training output deserves promotion readiness. Shadow uses realtime data during
live market hours to compare already-promoted models and choose the production
active model inside `trading-execution`.

Evaluation evidence is SQL-backed under the `trading_evaluation` schema. Replay
contracts, replay dataset freeze state, replay execution runs, replay decisions,
fold settlement, promotion eligibility, promotion readiness, and promoted-model
parameters are table state; storage artifacts remain detail/report payloads.

Current settlement status is `review_required` for the crypto fixed-sleeve Replay because AUROC is below the minimum gate. Current settlement evidence therefore does not support promotion readiness.

Agent review, when used, must follow the workspace skill `skills/openclaw/promotion-evaluation-review`. The reviewer produces advisory structured evidence only; deterministic evaluation code validates eligibility and writes promotion readiness records.

## Platform Boundaries

- `trading-model` owns training, model generation, and raw model outputs.
- `trading-evaluation` owns independent replay evaluation, fold settlement, promotion eligibility, and promotion readiness records.
- `trading-execution` owns live/shadow runtime model selection and active model switching after a market-hours shadow cycle.
- `trading-manager` owns scheduling and control-plane state, not model-quality judgment or activation.
- `trading-storage` owns durable settlement reports, references, backup, archive, restore, and lifecycle.
- `trading-execution` owns broker/exchange execution and account mutation.

Shared names, fields, statuses, scripts, and contract ids discovered here must be registered through `trading-manager` before other repositories depend on them.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src scripts
PYTHONPATH=src python3 scripts/evaluation/validate_replay_contract.py --input tests/fixtures/replay_contract_valid.json
PYTHONPATH=src python3 scripts/evaluation/build_promotion_readiness_record.py --promotion-eligibility-json tests/fixtures/promotion_eligibility_eligible.json --candidate-model-ref storage://models/market_regime/new --candidate-config-ref storage://configs/market_regime/new --rollback-ref storage://models/market_regime/old
```
