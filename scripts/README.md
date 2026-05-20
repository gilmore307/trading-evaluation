# Scripts

Executable wrappers for evaluation helpers.

Scripts are thin entrypoints over `src/trading_evaluation/` and must not own reusable business logic.

Current entrypoints:

- `evaluation/validate_benchmark_contract.py` validates benchmark contracts.
- `evaluation/prepare_benchmark_dataset.py` prepares storage-side benchmark dataset manifests and fail-closed task keys.
- `evaluation/build_promotion_readiness_record.py` builds promotion readiness records from eligible evaluation decisions.
