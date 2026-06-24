# Replay Contracts

## Promotion Replay Requirements

The promotion replay must be selected once and then frozen. For M02 and later target-selection models, the replay is a historical-clock candidate-policy replay. It freezes the candidate-generation policy and historical replay substrate, not a hand-picked list of final trade targets.

Required properties:

- one replay contract with field `replay_mode = candidate_policy_replay`.
- the canonical five-year replay window `2021-01-01` through `2026-01-01` end-exclusive, candidate fold id, and base-context artifact for the M01/M02 replay substrate.
- a frozen base source snapshot, candidate policy, cost model, baseline ladder, selection metrics, and guardrails.
- a fixed replay initial capital of `25000.0` `USD` for replay equity-path diagnostics, dollar PnL normalization, and charting; this is not broker/account state and replay still performs no account mutation.
- candidate policy inputs covering point-in-time M01 background-context sector or industry opportunity evidence, reviewed target-context mappings or proxies, market-wide hot/liquid-name admission rules, quality filters, and control candidates when contrast is required.
- replay must execute through `trading-execution`'s `execution_runtime_component_graph` under Replay adapters. Models are point-in-time evidence consumed by the components, not the replay execution unit.
- equity/options replay allocation is ranked best-first inside a finite portfolio-capacity contract. The default equity/options sleeve has five simultaneous risk slots, derived from the default `0.20` target-allocation fraction. M04 must emit the target allocation as a fraction of total portfolio/account budget. Replay converts that model fraction to a minimum new-target notional floor; the default target-allocation fraction is only a fallback when the model field is missing. For listed options, replay buys one contract when a single contract costs more than the model-derived floor, and otherwise rounds contract count up so planned notional is at least that floor while cash and position-capacity remain available. Research runs may request an explicit wider or unbounded position-count override, but such receipts are not promotion-compatible.
- no `target_symbol` or contract-level `target_refs`; use `candidate_fold_id` for fold binding and `base_context_ref` for the M01/M02 base-context scope.
- metrics must evaluate realized replay performance after cost, risk, drawdown, turnover, selection quality, and guardrails.
- metadata for candidate source, M01 background-context state, target-context source, event state, data availability, and model decision provenance.
- explicit sector coverage metadata, including consumer and entertainment/media coverage.
- enough length to reduce accident and one-off event bias; the canonical five-calendar-year replay window is the ordinary promotion replay horizon.
- diverse market conditions: trend, drawdown, volatility regime changes, event shocks, and transition periods.
- explicit event coverage metadata for earnings-crossing windows, policy/macro shocks, liquidity or squeeze events, product-cycle repricing, and crypto-cycle events.
- deliberate point-in-time admission of then-hot thematic single-name candidates through C01 and the accepted candidate policy, including names outside the selected ETF universe when target-context review exists.
- a small crypto sleeve because crypto is a future primary execution focus.
- a small controlled stress sleeve for critical data-edge cases such as crypto missing quote/order-book context, sparse bars, missing M02 context, or partial event coverage.
- no leakage from the frozen replay window into training-used folds.
- any fold that intersects the sealed promotion replay window must be skipped or blocked for candidate training.
- fixed data snapshot, cost model, slippage/fee assumptions, and baseline ladder.
- fixed initial capital of `25000.0` USD for all candidate-policy replay runs so replay performance K-lines and ETF/context comparisons use the same account-size denominator.
- replay acquisition and event/source normalization are construction phases that
  produce a frozen base data snapshot for the explicit model fold and replay
  window.
- candidate equity, symbol-scoped liquidity/news, option-chain,
  selected-contract path, and other sparse or high-cost evidence discovered
  during replay follow the demand-driven acquisition contract in
  `docs/03_contracts.md`: known intervals are fetched exactly, unknown duration
  tracking extends by monotonic forward staging chunks, and future staged rows
  or coverage metadata stay decision-invisible until the replay pointer reaches
  them.
- all replay, settlement, promotion eligibility, guardrail, and regression checks for that scope must reuse that frozen data snapshot instead of rebuilding data per model candidate.
- replay evaluation must run through the execution runtime component graph under a historical clock, not through the model training pipeline or an evaluation-owned trading decision graph.
- replay must not run `execution_shadow_cycle_selection`; shadow-cycle selection is a realtime execution mechanism for already-promoted models, not a historical evaluation mechanism for training outputs.
- reviewed target-context refs available to the candidate policy so non-ETF targets still use the accepted target/proxy mapping route.

Required replay behavior:

- the execution runtime component graph gets the full replay period and must operate according to the same component route intended for live use.
- each decision advances an explicit `replay_time_pointer`; C01-C07 decision inputs may consume only evidence available at or before that pointer. Data after the pointer is unavailable until settlement, where it may be used only for labels, simulated fills, option contract paths, and realized-return evaluation.
- M01 produces point-in-time background context over broad market, sector, and industry state; C01 reads that evidence, account state, positions, market universe, and watch/admission policy to create candidate-entry and open-position pools.
- C02-C07 decide entry, lifecycle, option review, order intent, execution gate, and failure review. Downstream model outputs are consumed inside those component contracts rather than used as an evaluation-owned execution route.
- C05 replay sizing records planned option quantity from the selected contract cost and the M04 target-allocation fraction times total budget; C06 may verify but must not alter that quantity.
- M06 ResidualEventGovernance remains an independent model surface and is invoked only through execution-owned failure review or other accepted residual-governance component inputs after observed model or trade failure.
- the replay judges final realized replay performance and guardrail behavior, not isolated hand-picked episodes.
- replay output must preserve enough per-decision evidence to audit why targets were selected, watched, blocked, traded, or skipped.
- each `evaluation_replay_decision_row` must carry `model_layer_refs` and `model_layer_diagnostics` for the model-backed component surfaces that shaped the row. At minimum, C01-C03 context surfaces need component-internal score diagnostics, C04/M04 needs unified-decision diagnostics, C05/M05 needs option-expression selection diagnostics and explicit model ref, and C08/M06 needs residual-event action-surface diagnostics and explicit model ref when invoked. Missing selected option paths are C06 materialization censoring and must not be mixed into model win-rate statistics.

Suggested promotion-benchmark replay coverage:

- the full 2021-2025 period, with enough different market states to avoid a one-regime replay.
- consumer discretionary, consumer staples, entertainment/media, technology/AI, energy, healthcare, financials, broad-market, and crypto context should be reachable through the candidate policy when point-in-time conditions support them.
- event-heavy periods, earnings periods, liquidity stress, strong trend, drawdown, rotation, and high-volatility states should appear naturally in the replay window.

Do not concatenate replay histories into one opaque series for judgment. Each month, market regime, candidate source, selected/top-N group, watch/blocked group, trade/skip reason, guardrail, and risk slice should produce its own metrics; the final decision uses the full replay result plus slice diagnostics.

## Guardrails

Guardrail replays may catch overfit or pathological candidates. They should not replace the promotion replay leaderboard unless a new replay contract is explicitly accepted.

## Current Selection Status

The current model-group replay dataset is an explicit model-fold and M01/M02 base-context snapshot over the canonical five-year replay window. A frozen dataset or replay receipt is eligible only when its fold id matches the completed fold. The training target symbol is manager-owned model selection context; replay does not carry it and it does not constrain the replay trading scope.

Do not use ad hoc target/window panels for training, tuning, prompt iteration, model selection, or promotion. Full promotion judgment requires an accepted candidate-policy replay with explicit fold, base-context scope, and execution-component replay path.
