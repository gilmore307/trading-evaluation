# Scripts

Executable wrappers for evaluation helpers.

Scripts are thin entrypoints over `src/trading_evaluation/` and must not own reusable business logic.

Current entrypoints:

- `evaluation/validate_replay_contract.py` validates replay contracts.
- `evaluation/prepare_replay_dataset.py` prepares storage-side replay dataset manifests and one-shot acquisition requirements.
- `evaluation/run_replay_acquisition.py` plans or executes bounded one-shot replay feed acquisitions from `feed_acquisition_plan.csv`.
- `evaluation/validate_benchmark_contract.py`, `evaluation/prepare_benchmark_dataset.py`, and `evaluation/run_benchmark_acquisition.py` remain compatibility entrypoints.
- `evaluation/build_fold_settlement_run.py` assembles fold-settlement metrics, including AUROC and structure diagnostics, from replay decision rows.
- `evaluation/build_promotion_readiness_record.py` builds promotion readiness records from eligible evaluation decisions.
