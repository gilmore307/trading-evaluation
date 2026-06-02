# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns replay judgment, fold settlement, promotion eligibility, and promotion readiness records. It does not train models, schedule workflow, store durable artifacts, switch active model configs, execute broker actions, or mutate accounts.

## D002 - Fixed Target Panels Are Not Promotion Replay

Date: 2026-05-19
Status: Superseded by D004.

Fixed target panels do not support target-selection promotion replay because they preselect the final target identity. D004 defines the active candidate-policy replay contract.

## D003 - Promotion Readiness Belongs In Evaluation; Runtime Activation Belongs In Execution

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns offline promotion readiness because manager should remain a scheduler. Runtime active model selection belongs to `trading-execution` after a market-hours shadow cycle compares the active model and promoted-but-not-active candidates.

Replay and shadow are separate mechanisms. Replay uses a fixed historical
window and frozen historical data to evaluate whether a training output has
promotion value. Shadow uses realtime market data during live market hours to
compare already-promoted models for production active-model selection. Replay
must not call execution's shadow-cycle roster selector.

## D004 - Promotion Replay Freezes Candidate Policy, Not Final Targets

Date: 2026-05-20
Status: Accepted

For Layer 3 and later target-selection models, promotion replay gives the execution runtime component graph a fixed historical clock over `2021-01-01` through `2026-01-01` end-exclusive. This covers the full 2021-2025 calendar years and 1255 expected NYSE trading days. The replay fixes the replay window, base source snapshot, cost model, baseline ladder, guardrails, Layer 2 sector-selection inputs, sector constituent/proxy rules, hot/liquid-name admission rules, quality filters, controls, and scoring metrics.

It must not preselect final tickers or run a model-owned trading path. Replay calls `trading-execution`'s `execution_runtime_component_graph` under the historical clock and Replay adapters. Models provide point-in-time evidence consumed by the components; C01-C07 own intake, target admission, entry, lifecycle, option review, order intent, execution gating, and failure review. Fixed target/window panels are not applicable to promotion replay judgment.

## D005 - Replay Uses The Execution Runtime Component Graph

Date: 2026-05-21
Status: Accepted

Replay and live/shadow execution use the same task-level execution components and decision contracts. Replay swaps only the adapter profile: historical clock, frozen historical market snapshot, simulated account, simulated execution gate, and fill simulator.

`trading-evaluation` owns replay orchestration, freeze validation, settlement, metrics, promotion eligibility, and promotion readiness. It must not reimplement target selection, entry, position lifecycle, option re-expression, failure explanation, order intent, or execution-gate decisions outside `trading-execution`.

Replay output may admit a candidate to shadow review through promotion
readiness, but it does not choose among active/shadow production models. That
choice belongs to the execution-owned shadow cycle after realtime evidence
matures.

Layer 10 remains an independent model, but Replay reaches it only through execution's Failure Explanation Component after observed model or trade failure. Normal entry and position lifecycle event risk remains Layer 4's forward-risk responsibility.
