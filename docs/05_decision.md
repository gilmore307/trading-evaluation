# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, promotion eligibility, and promotion readiness records. It does not train models, schedule workflow, store durable artifacts, switch active model configs, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Panel

Date: 2026-05-19
Status: Accepted

The primary benchmark may use multiple fixed target/window components inside one frozen panel so fold settlement remains horizontally comparable across model generations.

The panel must be long enough to reduce accident, structurally complex enough to cover diverse market states, and excluded from candidate training by target/window. If a target appears in a benchmark component, any same-target training fold that overlaps that component window must be skipped or blocked. The target may still be trained outside sealed benchmark windows.

## D003 - Promotion Readiness Belongs In Evaluation; Runtime Activation Belongs In Execution

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns offline promotion readiness because manager should remain a scheduler. Runtime active model selection belongs to `trading-execution` after a market-hours shadow cycle compares the active model and promoted-but-not-active candidates.
