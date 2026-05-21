# Replay Contracts

## Promotion Replay Requirements

The promotion replay must be selected once and then frozen. For Layer 3 and later target-selection models, the replay is a historical-clock candidate-policy replay. It freezes the candidate-generation policy and historical replay substrate, not a hand-picked list of final trade targets.

Required properties:

- one replay contract with field `replay_mode = candidate_policy_replay`.
- the canonical fixed replay window `2021-01-01` through `2026-01-01` end-exclusive, covering the full 2021-2025 calendar years and 1255 expected NYSE trading days.
- a frozen candidate-universe policy, historical data snapshot, cost model, baseline ladder, selection metrics, and guardrails.
- candidate policy inputs covering current Layer 2 selected/watch sectors, reviewed sector constituents or proxies, current market-wide hot/liquid names, quality filters, and control candidates when contrast is required.
- the model must generate candidates, rank/select targets, and run through `trading-execution`'s `execution_runtime_component_graph` under Replay adapters.
- no `target_symbol`, fixed final target list.
- metrics must evaluate realized replay performance after cost, risk, drawdown, turnover, selection quality, and guardrails.
- metadata for candidate source, market state, Layer 2 sector source, event state, data availability, and model decision provenance.
- explicit sector coverage metadata, including consumer and entertainment/media coverage.
- enough length to reduce accident and one-off event bias; the canonical five-calendar-year window is fixed for all ordinary promotion comparisons.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- explicit event coverage metadata for earnings-crossing windows, policy/macro shocks, liquidity or squeeze events, product-cycle repricing, and crypto-cycle events.
- deliberate point-in-time admission of then-hot thematic single-name candidates through the candidate policy, including names outside the selected ETF universe when target-context review exists.
- a small crypto sleeve because crypto is a future primary execution focus.
- a small controlled stress sleeve for critical data-edge cases such as crypto missing quote/order-book context, sparse bars, missing Layer 2 context, or partial event coverage.
- no leakage from the frozen replay window into training-used folds.
- any fold that intersects the sealed promotion replay window must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.
- replay acquisition and event/source normalization are one-time construction phases that produce a frozen reusable data snapshot for the contract.
- all replay, settlement, promotion eligibility, guardrail, and regression checks must reuse that frozen data snapshot instead of rebuilding data per model candidate.
- replay evaluation must run through the execution runtime component graph under a historical clock, not through the model training pipeline or an evaluation-owned trading decision graph.
- reviewed target-context refs available to the candidate policy so non-ETF targets still use the accepted target/proxy mapping route.

Required replay behavior:

- the candidate model gets the full replay period and must operate according to the same model route intended for live use.
- Layer 2 produces sector context point-in-time; Layer 3 generates/ranks the candidate set; downstream layers decide whether and how to trade.
- Layer 4 and later are invoked per selected target. If Layer 3 selects multiple targets, replay fans them out into repeated single-target downstream runs rather than passing one multi-target batch into Layer 4+; Layer 6 dynamic risk policy is still driven primarily by whole-market state, not by one sector or target.
- Layer 10 EventRiskGovernor remains an independent model and is invoked only through the execution-owned Failure Explanation Component after observed model or trade failure.
- the replay judges final realized replay performance and guardrail behavior, not isolated hand-picked episodes.
- replay output must preserve enough per-decision evidence to audit why targets were selected, watched, blocked, traded, or skipped.

Suggested replay coverage:

- the full 2021-2025 period, with enough different market states to avoid a one-regime replay.
- consumer discretionary, consumer staples, entertainment/media, technology/AI, energy, healthcare, financials, broad-market, and crypto context should be reachable through the candidate policy when point-in-time conditions support them.
- event-heavy periods, earnings periods, liquidity stress, strong trend, drawdown, rotation, and high-volatility states should appear naturally in the replay window.

Do not concatenate replay histories into one opaque series for judgment. Each month, market regime, candidate source, selected/top-N group, watch/blocked group, trade/skip reason, guardrail, and risk slice should produce its own metrics; the final decision uses the full replay result plus slice diagnostics.

## Guardrails

Guardrail replays may catch overfit or pathological candidates. They should not replace the promotion replay leaderboard unless a new replay contract is explicitly accepted.

## Current Selection Status

The canonical promotion replay window is fixed as `2021-01-01` through `2026-01-01` end-exclusive. The full replay is not frozen until the reusable data snapshot, cost model, baselines, guardrails, and selection metrics are accepted. The prior fixed target/window artifact was deleted because it preselected final targets and is no longer applicable.

Do not use fixed target/window panels for training, tuning, prompt iteration, model selection, or promotion. Full promotion judgment requires an accepted candidate-policy replay.
