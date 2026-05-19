# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, promotion eligibility, and promotion readiness records. It does not train models, schedule workflow, store durable artifacts, switch active model configs, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Target Window

Date: 2026-05-19
Status: Accepted

The primary benchmark uses one fixed target and one fixed time window so fold settlement remains horizontally comparable across model generations.

The benchmark window must be long enough to reduce accident, structurally complex enough to cover diverse market states, and excluded from training. The target must not be a training-used target.

## D003 - Promotion Readiness Belongs In Evaluation; Runtime Activation Belongs In Execution

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns offline promotion readiness because manager should remain a scheduler. Runtime active model selection belongs to `trading-execution` after a market-hours shadow cycle compares the active model and promoted-but-not-active candidates.
