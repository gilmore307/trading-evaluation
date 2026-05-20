# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, promotion eligibility, and promotion readiness records. It does not train models, schedule workflow, store durable artifacts, switch active model configs, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Panel

Date: 2026-05-19
Status: Superseded and deleted for target-selection promotion benchmarks by D004.

The primary benchmark previously allowed multiple fixed target/window components inside one frozen panel so fold settlement remained horizontally comparable across model generations.

That fixed-panel route is no longer active because it preselects the final target identity the model is supposed to choose.

## D003 - Promotion Readiness Belongs In Evaluation; Runtime Activation Belongs In Execution

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns offline promotion readiness because manager should remain a scheduler. Runtime active model selection belongs to `trading-execution` after a market-hours shadow cycle compares the active model and promoted-but-not-active candidates.

## D004 - Promotion Benchmark Freezes Candidate Policy, Not Final Targets

Date: 2026-05-20
Status: Accepted

For Layer 3 and later target-selection models, promotion benchmarking must give the candidate model a fixed historical-clock replay over `2021-01-01` through `2026-01-01` end-exclusive. This covers the full 2021-2025 calendar years and 1255 expected NYSE trading days. The benchmark fixes the replay window, source snapshot, cost model, baseline ladder, guardrails, Layer 2 sector-selection inputs, sector constituent/proxy rules, hot/liquid-name admission rules, quality filters, controls, and scoring metrics.

It must not preselect the final tickers the model is supposed to choose. The model must generate candidates from the accepted policy, rank/select targets, run through the realtime decision route under the historical clock, and be judged by final realized replay performance plus slice diagnostics. Fixed target/window panels are not applicable to promotion benchmark judgment.
