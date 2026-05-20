"""Independent benchmark, settlement, and promotion-readiness helpers."""

from .benchmark import (
    BenchmarkContract,
    BenchmarkValidation,
    is_training_fold_blocked_by_benchmark,
    validate_benchmark_contract,
)
from .benchmark_dataset import (
    BENCHMARK_COVERAGE_SUMMARY_CONTRACT,
    BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT,
    BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT,
    BENCHMARK_REPLAY_WINDOW_MANIFEST_CONTRACT,
    PreparedBenchmarkDataset,
    prepare_benchmark_dataset,
)
from .promotion import (
    PROMOTION_ELIGIBILITY_DECISION_CONTRACT,
    PROMOTION_READINESS_RECORD_CONTRACT,
    build_promotion_eligibility_decision,
    build_promotion_readiness_record,
    validate_promotion_eligibility_decision,
    validate_promotion_readiness_record,
)

__all__ = [
    "BenchmarkContract",
    "BenchmarkValidation",
    "BENCHMARK_COVERAGE_SUMMARY_CONTRACT",
    "BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT",
    "BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT",
    "BENCHMARK_REPLAY_WINDOW_MANIFEST_CONTRACT",
    "PROMOTION_ELIGIBILITY_DECISION_CONTRACT",
    "PROMOTION_READINESS_RECORD_CONTRACT",
    "PreparedBenchmarkDataset",
    "build_promotion_eligibility_decision",
    "build_promotion_readiness_record",
    "is_training_fold_blocked_by_benchmark",
    "prepare_benchmark_dataset",
    "validate_benchmark_contract",
    "validate_promotion_eligibility_decision",
    "validate_promotion_readiness_record",
]
