# Scripts

Executable wrappers for evaluation helpers.

Scripts are thin entrypoints over `src/trading_evaluation/` and must not own reusable business logic.

Current entrypoints:

- `evaluation/validate_replay_contract.py` validates replay contracts.
- `evaluation/prepare_replay_dataset.py` prepares storage-side replay dataset manifests and one-shot acquisition requirements.
- `evaluation/run_replay_acquisition.py` plans or executes bounded one-shot replay feed acquisitions from `feed_acquisition_plan.csv`.
- `evaluation/freeze_replay_dataset.py` validates accepted coverage and freezes a prepared replay dataset by writing `replay_freeze_receipt.json`.
- `evaluation/run_replay_runtime_dry_run.py` smoke-tests the execution-owned Replay component graph without provider, model activation, broker, or account side effects.
- `evaluation/run_replay_execution.py` runs candidate-policy Replay over frozen OKX crypto bars and materialized Alpaca equity bars, then writes settlement-ready decision rows. Use `--exclude-equity` only for a crypto-sleeve compatibility run.
- `evaluation/build_fold_settlement_run.py` assembles fold-settlement metrics, including AUROC and structure diagnostics, from replay decision rows.
- `evaluation/build_promotion_evaluation_review.py` builds promotion-evaluation-review evidence and a promotion eligibility decision from settlement output.
- `evaluation/build_promotion_readiness_record.py` builds promotion readiness records from eligible evaluation decisions.
