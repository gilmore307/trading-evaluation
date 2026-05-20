# Benchmark Contracts

## Promotion Benchmark Requirements

The promotion benchmark must be selected once and then frozen. For Layer 3 and later target-selection models, the benchmark freezes the candidate-generation policy and historical replay substrate, not a hand-picked list of final trade targets.

Required properties:

- one benchmark contract with a frozen candidate-universe policy, historical windows, data snapshot, cost model, baseline ladder, and guardrails.
- candidate policy inputs covering current Layer 2 selected/watch sectors, reviewed sector constituents or proxies, current market-wide hot/liquid names, quality filters, and control candidates when contrast is required.
- fixed policy weights or scoring weights for composite settlement.
- metadata for sector, theme, asset class, event, data availability, component role, and candidate source.
- explicit sector coverage metadata, including consumer and entertainment/media coverage.
- enough length to reduce accident and one-off event bias.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- explicit event coverage metadata for earnings-crossing windows, policy/macro shocks, liquidity or squeeze events, product-cycle repricing, and crypto-cycle events.
- deliberate point-in-time admission of then-hot thematic single-name candidates, including names outside the selected ETF universe when target-context review exists.
- a small crypto sleeve because crypto is a future primary execution focus.
- a small controlled stress sleeve for critical data-edge cases such as crypto missing quote/order-book context, sparse bars, missing Layer 2 context, or partial event coverage.
- no leakage from frozen replay windows into training-used folds.
- any fold that intersects sealed promotion replay windows and could learn the benchmark candidate-policy outcome must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.
- benchmark acquisition and event/source normalization are one-time construction phases that produce a frozen reusable data snapshot for the contract.
- all benchmark replay, settlement, promotion eligibility, guardrail, and regression checks must reuse that frozen data snapshot instead of rebuilding data per model candidate.
- benchmark evaluation must run through the realtime execution decision path under a historical clock, not through the model training pipeline.
- reviewed target-context refs for single-name equity and crypto components so non-ETF targets still use the accepted target/proxy mapping route.
- stress-exception refs for components that deliberately violate normal data completeness assumptions.
- no fixed final ticker list for the model to select from unless the artifact is explicitly labeled as a diagnostic or stress panel rather than the promotion benchmark.

Suggested composition:

- at least 55% single-name optionable equity components.
- no more than 30% ETF components; ETFs are background anchors, not the main benchmark surface.
- at least 10 distinct sector coverage tags.
- consumer discretionary, consumer staples, and entertainment/media coverage.
- at least 10% earnings-crossing component weight.
- at least 25% event-driven component weight.
- substantial then-hot thematic single-name components from storage, optical modules, rare earth, nuclear, data center, AI, healthcare, meme/option-stress, or similar period-specific leadership themes.
- 5-15% crypto spot components.
- No single target, year, theme bucket, or market state should dominate the panel.
- Large same-background overlap should be limited. Components may share time periods only when each target adds genuinely different tradability, liquidity, option-expression, or thematic stress evidence.

Controlled stress sleeve:

- Stress components must use `component_role = stress_edge_case` or `guardrail_stress`.
- Critical stress tags such as `missing_quote_order_book_context` and `missing_layer2_context` are not allowed on ordinary primary components.
- Missing quote/order-book context stress components are accepted only for crypto components.
- Thematic single-name components may omit Layer 2 context only as an explicit stress exception, not as a normal target-routing shortcut.
- Aggregate stress component weight must stay capped at 15% of the panel.

Do not concatenate candidate-policy replay histories into one opaque series for judgment. Each window, policy source, selected/top-N group, watch/blocked group, control group, guardrail, and regime slice should produce its own metrics; the composite is a fixed-weight aggregate over those results.

## Fixed Target/Window Panels

Fixed target/window panels are still useful as diagnostics and stress tests. They can test data acquisition, replay wiring, option-expression behavior, liquidity edge cases, event coverage, and known historical episodes.

They are not sufficient promotion benchmarks for a target-selection model because they preselect the final target identity. A fixed panel may be promoted into the benchmark package only as a diagnostic or stress sleeve, or as historical windows used by a candidate-policy replay that rebuilds the candidate set point-in-time.

## Guardrails

Guardrail benchmarks may catch overfit or pathological candidates. They should not replace the promotion benchmark leaderboard unless a new benchmark contract is explicitly accepted.

## Current Selection Status

The first promotion benchmark is not frozen yet. The current fixed target/window review artifact is benchmarks/primary_benchmark_candidate_20260519.json, summarized in docs/21_primary_benchmark_candidate.md.

Do not use that fixed panel for training, tuning, prompt iteration, model selection, or promotion. It may become a reviewed diagnostic/stress panel after target/window exclusion proof and coverage review, but full promotion judgment requires an accepted candidate-policy replay benchmark.
