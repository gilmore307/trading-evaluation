# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, promotion eligibility, and promotion readiness records. It does not train models, schedule workflow, store durable artifacts, switch active model configs, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Panel

Date: 2026-05-19
Status: Superseded for target-selection promotion benchmarks by D004; retained for fixed target/window diagnostics and stress panels.

The primary benchmark may use multiple fixed target/window components inside one frozen panel so fold settlement remains horizontally comparable across model generations.

The panel must be long enough to reduce accident, structurally complex enough to cover diverse market states, and excluded from candidate training by target/window. If a target appears in a benchmark component, any same-target training fold that overlaps that component window must be skipped or blocked. The target may still be trained outside sealed benchmark windows.

The panel should include more than ETF constituents. It should deliberately include a controlled share of then-hot thematic single names and a small crypto sleeve because those are expected future live focus areas. Non-ETF targets require reviewed target-context/proxy refs before they can enter the panel.

The panel may also include a small controlled stress sleeve for data-edge cases that live execution must tolerate, including crypto with missing quote/order-book context and thematic single names with intentionally missing Layer 2 context. These components must be explicitly labeled as stress components, carry data-availability tags and a stress-exception ref, and remain capped so they test robustness without dominating primary benchmark judgment.

## D003 - Promotion Readiness Belongs In Evaluation; Runtime Activation Belongs In Execution

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns offline promotion readiness because manager should remain a scheduler. Runtime active model selection belongs to `trading-execution` after a market-hours shadow cycle compares the active model and promoted-but-not-active candidates.

## D004 - Promotion Benchmark Freezes Candidate Policy, Not Final Targets

Date: 2026-05-20
Status: Accepted

For Layer 3 and later target-selection models, promotion benchmarking must replay a fixed candidate-universe policy under a historical clock. The benchmark fixes windows, source snapshots, cost model, baseline ladder, guardrails, Layer 2 sector-selection inputs, sector constituent/proxy rules, hot/liquid-name admission rules, quality filters, controls, and scoring weights.

It must not preselect the final tickers the model is supposed to choose. Fixed target/window panels remain useful as diagnostics and controlled stress surfaces, but they are not sufficient evidence that Layer 3 can select tradable targets from the live candidate pool.
