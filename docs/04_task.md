# Tasks

## Active Tasks

- Review/freeze the first primary benchmark panel after dataset preparation coverage is inspected. Component target/window pairs must remain excluded from same-target training folds.
- Implement fold settlement metric assembly after the benchmark contract is accepted.
- Move remaining promotion eligibility and readiness logic out of manager/model paths into this repository in controlled slices.

## Recently Accepted

- Created `trading-evaluation` as the independent benchmark, fold-settlement, promotion-eligibility, and promotion-readiness repository.
- Implemented the first fixture-safe benchmark contract validator and CLI.
- Prepared the first benchmark dataset manifest route: component manifest, feed acquisition plan, and coverage summary under storage-owned runtime output. Benchmark acquisition is one-shot and does not use manager task/request rows.
