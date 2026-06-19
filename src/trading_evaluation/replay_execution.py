"""Side-effect-free Replay execution over frozen source artifacts.

This module orchestrates replay decisions through `trading-execution`. It reads
already-frozen local source artifacts and emits evaluation settlement views over
execution-owned component outputs. Replay component artifacts must use the same
C01-C07 output contracts as live execution, with Replay adapter metadata. This
module does not call providers, train models, activate models, call brokers, or
mutate accounts.
"""

from __future__ import annotations

import csv
import inspect
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .execution_runtime import EXECUTION_REPLAY_ROUTE_REF, build_replay_runtime_dry_run

REPLAY_EXECUTION_RUN_CONTRACT = "evaluation_replay_execution_run"
REPLAY_DECISION_ROW_CONTRACT = "evaluation_replay_decision_row"
REPLAY_PROGRESS_CONTRACT = "evaluation_replay_progress"
PORTFOLIO_TRACE_AUDIT_CONTRACT = "candidate_policy_portfolio_trace_audit"
PORTFOLIO_TRACE_AUDIT_ROW_CONTRACT = "candidate_policy_portfolio_trace_audit_row"
ENTRY_THRESHOLD_CALIBRATION_CONTRACT = "validation_entry_threshold_calibration"
RUNTIME_COMPONENT_OUTPUT_CONTRACTS = (
    "execution_intake_snapshot",
    "entry_decision",
    "position_lifecycle_decision",
    "option_reexpression_decision",
    "execution_order_intent",
    "execution_gate_result",
    "failure_explanation_packet",
)
CRYPTO_SPOT_ACCOUNT_SLEEVE = "crypto_spot_account"
EQUITY_OPTIONS_ACCOUNT_SLEEVE = "equity_options_account"
CRYPTO_SYMBOLS_BY_INSTRUMENT = {
    "BTC-USDT": "BTC",
    "ETH-USDT": "ETH",
    "SOL-USDT": "SOL",
}
EQUITY_SOURCE_ROOT = Path("/root/projects/trading-storage/storage/01_source_data/monthly_backfill/alpaca_bars")
DEFAULT_DATASET_ROOT = Path("/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy")
DEFAULT_DB_URL_FILE = Path("/root/secrets/openclaw/database-url")
DEFAULT_CANDIDATE_UNIVERSE_FILENAME = "historical_candidate_universe.csv"
MODEL_EVIDENCE_CHAIN = (
    "model_01_market_regime_state",
    "model_02_sector_context_state",
    "model_03_target_state_vector_state",
    "model_03_event_state",
    "model_04_event_failure_risk",
    "model_05_alpha_confidence",
    "model_04_unified_decision",
    "model_05_option_expression",
    "model_06_residual_event_governance",
)
DEFAULT_ENTRY_ALPHA_THRESHOLD = 0.50
DEFAULT_MINIMUM_TRADE_INTENSITY = 0.05
DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT = 3
MINIMUM_ENTRY_ALPHA_THRESHOLD = 0.50
MINIMUM_CALIBRATION_OBSERVATION_COUNT = 60
MINIMUM_CALIBRATION_SELECTED_TRADE_COUNT = 5
MINIMUM_CALIBRATION_ALPHA_UNIQUE_VALUES = 3
MINIMUM_CALIBRATION_ALPHA_STDEV = 0.0001
REPLAY_COST_PER_FILLED_DECISION = 0.0015
DEFAULT_REPLAY_INITIAL_CAPITAL_USD = 25_000.0
DEFAULT_PORTFOLIO_MAX_POSITIONS = 0
DEFAULT_TARGET_ALLOCATION_FRACTION = 0.20
US_OPTION_CONTRACT_MULTIPLIER = 100.0
NEW_YORK = ZoneInfo("America/New_York")
REPLAY_INITIAL_CAPITAL_CURRENCY = "USD"
_GENERATOR_PARAMETER_CACHE: dict[int, set[str]] = {}
DISALLOWED_PLACEHOLDER_CANDIDATE_MODEL_REFS = (
    "trading-model://candidate_policy_replay/current_deterministic_crypto_policy",
)
REPLAY_OPTION_FEATURE_ACQUISITION_REQUIRED = "replay_option_feature_acquisition_required"
REPLAY_OPTION_FEATURE_FUTURE_DATA_REJECTED = "replay_option_feature_future_data_rejected"
REPLAY_OPTION_FEATURE_MISSING_SAMPLE_LIMIT = 100
OPTION_SOURCE_UNAVAILABLE_SNAPSHOT_TYPE = "source_unavailable"
OPTION_SOURCE_UNAVAILABLE_STATUS = "option_source_unavailable"
OPTION_SOURCE_UNAVAILABLE_SYMBOL = "__OPTION_SOURCE_UNAVAILABLE__"
REPLAY_TIME_POINTER_POLICY_REF = "replay_time_pointer_excludes_future_decision_inputs"
OPTION_CANDIDATE_POINT_IN_TIME_SAMPLE_LIMIT = 20
OPTION_EXPRESSION_SIGNAL_ACTION_TYPES = frozenset(
    {
        "open_long",
        "open_short",
        "bearish_underlying_path_but_no_short_allowed",
    }
)
OPTION_EXPRESSION_CURRENT_ENTRY_STYLES = frozenset({"limit_near_mid"})
OPTION_CANDIDATE_POINT_IN_TIME_FIELDS = (
    "snapshot_time",
    "available_time",
    "tradeable_time",
    "option_quote_available_time",
    "quote_timestamp",
    "underlying_timestamp",
    "source_available_time",
)


@dataclass(frozen=True)
class ReplayExecutionResult:
    """Replay execution receipt and decision-row output paths."""

    receipt_path: Path
    decision_rows_path: Path
    progress_path: Path
    receipt: dict[str, Any]


@dataclass(frozen=True)
class PortfolioTraceAuditResult:
    """Portfolio-constrained trace audit paths and summary payload."""

    summary_path: Path
    trace_rows_path: Path
    entry_calibration_path: Path
    summary: dict[str, Any]


@dataclass(frozen=True)
class EntryCalibration:
    """Validation-selected entry gates for replay action conversion."""

    artifact: dict[str, Any]
    path: Path

    @property
    def minimum_entry_alpha_confidence(self) -> float:
        return float(self.artifact["selected_thresholds"]["minimum_entry_alpha_confidence"])

    @property
    def minimum_trade_intensity(self) -> float:
        return float(self.artifact["selected_thresholds"]["minimum_trade_intensity"])


def build_crypto_replay_execution_run(
    *,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    output_dir: Path | None = None,
    run_id: str | None = None,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any] | None,
    after_cost_alpha_model_ref: str | None = None,
    replay_contract_ref: str = "trading-evaluation/replays/promotion_replay_candidate_policy.json",
    max_decision_rows: int | None = None,
    generated_at_utc: str | None = None,
    progress_path: Path | None = None,
    calibration_window_month_count: int = DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT,
    initial_capital_usd: float = DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
) -> ReplayExecutionResult:
    """Run the frozen crypto sleeve through the execution-owned Replay route."""
    return build_candidate_policy_replay_execution_run(
        dataset_root=dataset_root,
        output_dir=output_dir,
        run_id=run_id,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        after_cost_alpha_model_ref=after_cost_alpha_model_ref,
        replay_contract_ref=replay_contract_ref,
        max_decision_rows=max_decision_rows,
        generated_at_utc=generated_at_utc,
        progress_path=progress_path,
        calibration_window_month_count=calibration_window_month_count,
        initial_capital_usd=initial_capital_usd,
        include_equity=False,
    )


def build_candidate_policy_replay_execution_run(
    *,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    output_dir: Path | None = None,
    run_id: str | None = None,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any] | None,
    after_cost_alpha_model_ref: str | None = None,
    replay_contract_ref: str = "trading-evaluation/replays/promotion_replay_candidate_policy.json",
    max_decision_rows: int | None = None,
    generated_at_utc: str | None = None,
    progress_path: Path | None = None,
    calibration_window_month_count: int = DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT,
    include_crypto: bool = True,
    include_equity: bool = True,
    equity_source_root: Path = EQUITY_SOURCE_ROOT,
    equity_symbols: Sequence[str] | None = None,
    replay_month: str | None = None,
    option_feature_database_url: str | None = None,
    option_feature_schema: str = "trading_data",
    option_feature_table: str = "model_05_option_expression_feature_generation",
    option_contract_path_table: str = "model_05_option_expression_data_acquisition_contract_path",
    candidate_handoff_database_url: str | None = None,
    candidate_handoff_schema: str = "trading_data",
    candidate_handoff_table: str = "model_02_sector_context_data_acquisition",
    candidate_universe_path: Path | None = None,
    initial_capital_usd: float = DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
    portfolio_max_positions: int = DEFAULT_PORTFOLIO_MAX_POSITIONS,
    portfolio_default_target_allocation_fraction: float = DEFAULT_TARGET_ALLOCATION_FRACTION,
    portfolio_switch_minimum_rank_score_delta: float = 0.05,
) -> ReplayExecutionResult:
    """Run candidate-policy replay over frozen crypto plus materialized equity bars."""

    candidate_model_ref = _require_candidate_model_ref(candidate_model_ref)
    if after_cost_alpha_model is None:
        raise ValueError("after_cost_alpha_model is required for replay Layer 5 inference")
    _validate_after_cost_alpha_model_for_replay(after_cost_alpha_model)
    initial_capital_usd = _validated_initial_capital_usd(initial_capital_usd)
    _validate_portfolio_replay_policy(
        max_positions=portfolio_max_positions,
        default_target_allocation_fraction=portfolio_default_target_allocation_fraction,
        switch_minimum_rank_score_delta=portfolio_switch_minimum_rank_score_delta,
    )
    manifest = _load_json(dataset_root / "dataset_manifest.json")
    freeze_receipt_path = dataset_root / "replay_freeze_receipt.json"
    freeze_receipt: dict[str, Any] | None = None
    plan_path = Path(str(manifest["feed_acquisition_plan_ref"]))
    if replay_month:
        _validate_replay_month_coverage(plan_path=plan_path, replay_month=replay_month)
    else:
        freeze_receipt = _load_json(freeze_receipt_path)
        _validate_frozen_dataset(manifest, freeze_receipt)
    resolved_option_feature_database_url = (
        _default_option_feature_database_url() if option_feature_database_url is None else option_feature_database_url
    )
    resolved_candidate_handoff_database_url = (
        resolved_option_feature_database_url
        if candidate_handoff_database_url is None
        else candidate_handoff_database_url
    )
    candidate_handoff = _candidate_handoff_for_replay(
        database_url=resolved_candidate_handoff_database_url,
        schema=candidate_handoff_schema,
        table=candidate_handoff_table,
        candidate_universe_path=_resolved_candidate_universe_path(
            dataset_root=dataset_root,
            candidate_universe_path=candidate_universe_path,
        ),
        explicit_equity_symbols=equity_symbols,
        include_equity=include_equity,
        replay_month=replay_month,
    )
    generated_at = generated_at_utc or _now_utc()
    run_id = run_id or f"candidate_policy_replay_{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    output_dir = output_dir or dataset_root / "replay_execution_runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_rows_path = output_dir / "decision_rows.jsonl"
    receipt_path = output_dir / "replay_execution_receipt.json"
    progress_path = progress_path or dataset_root / "replay_progress.jsonl"
    calibration_path = output_dir / "entry_threshold_calibration.json"
    option_feature_requirements_path = output_dir / "option_feature_requirements.jsonl"

    bars_by_target = _load_candidate_policy_bars(
        plan_path=plan_path,
        include_crypto=include_crypto,
        include_equity=include_equity,
        equity_source_root=equity_source_root,
        equity_symbols=candidate_handoff["candidate_symbols"],
        replay_month=replay_month,
    )
    if not bars_by_target:
        raise ValueError("candidate-policy replay found no materialized market bars")
    candidate_handoff = _prune_fixed_candidate_handoff_no_history_symbols(
        candidate_handoff=candidate_handoff,
        bars_by_target=bars_by_target,
        equity_source_root=equity_source_root,
        replay_month=replay_month,
    )
    _validate_equity_candidate_bar_coverage(
        include_equity=include_equity,
        explicit_equity_symbols=equity_symbols,
        candidate_handoff=candidate_handoff,
        bars_by_target=bars_by_target,
    )
    option_candidates_by_underlying_time = _LazyOptionCandidateFeatures(
        database_url=resolved_option_feature_database_url,
        schema=option_feature_schema,
        table=option_feature_table,
    )
    option_contract_paths_by_symbol = _load_option_contract_path_bars(
        database_url=resolved_option_feature_database_url,
        schema=option_feature_schema,
        table=option_contract_path_table,
        targets=bars_by_target.keys(),
    )
    market_dates = sorted({row["date"] for rows in bars_by_target.values() for row in rows})
    entry_calibration = _build_entry_calibration(
        bars_by_target=bars_by_target,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        replay_contract_ref=replay_contract_ref,
        generated_at_utc=generated_at,
        output_path=calibration_path,
        validation_month_count=calibration_window_month_count,
        max_decision_rows=max_decision_rows,
    )
    (
        selected_equity_replay_keys,
        precomputed_layer_outputs,
        precomputed_option_expression_plans,
        portfolio_selection_summary,
    ) = _select_candidate_policy_portfolio_replay_keys(
        bars_by_target=bars_by_target,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        entry_calibration=entry_calibration,
        option_candidates_by_underlying_time=option_candidates_by_underlying_time,
        initial_capital_usd=initial_capital_usd,
        max_positions=portfolio_max_positions,
        default_target_allocation_fraction=portfolio_default_target_allocation_fraction,
        switch_minimum_rank_score_delta=portfolio_switch_minimum_rank_score_delta,
    )
    decision_rows = _build_candidate_policy_decision_rows(
        bars_by_target=bars_by_target,
        market_dates=market_dates,
        run_id=run_id,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        replay_contract_ref=replay_contract_ref,
        max_decision_rows=max_decision_rows,
        entry_calibration=entry_calibration,
        option_candidates_by_underlying_time=option_candidates_by_underlying_time,
        option_contract_paths_by_symbol=option_contract_paths_by_symbol,
        option_feature_requirements_path=option_feature_requirements_path,
        allow_option_feature_requirements=_candidate_handoff_allows_option_feature_requirements(candidate_handoff),
        selected_equity_replay_keys=selected_equity_replay_keys,
        precomputed_layer_outputs=precomputed_layer_outputs,
        precomputed_option_expression_plans=precomputed_option_expression_plans,
        total_portfolio_notional_usd=initial_capital_usd,
        default_target_allocation_fraction=portfolio_default_target_allocation_fraction,
    )
    option_replay_coverage = _option_replay_coverage_summary(
        bars_by_target=bars_by_target,
        option_candidates_by_underlying_time=option_candidates_by_underlying_time,
        option_contract_paths_by_symbol=option_contract_paths_by_symbol,
        decision_rows=decision_rows,
    )
    _write_jsonl(decision_rows_path, decision_rows)
    progress_rows = _build_replay_progress_rows(
        decision_rows=decision_rows,
        run_id=run_id,
        generated_at_utc=generated_at,
        receipt_path=receipt_path,
        decision_rows_path=decision_rows_path,
        initial_capital_usd=initial_capital_usd,
    )
    receipt = {
        "contract_type": REPLAY_EXECUTION_RUN_CONTRACT,
        "replay_execution_run_id": run_id,
        "execution_scope": "candidate_policy_replay_materialized_market_data",
        "replay_completion_scope": "bounded_diagnostic" if max_decision_rows is not None else "full_candidate_universe",
        "max_decision_rows": max_decision_rows,
        "initial_capital_usd": initial_capital_usd,
        "initial_capital": {
            "amount": initial_capital_usd,
            "currency": REPLAY_INITIAL_CAPITAL_CURRENCY,
            "role": (
                "finite_capital_portfolio_replay_budget"
                if include_equity
                else "replay_equity_path_and_return_normalization"
            ),
            "broker_or_account_state": False,
        },
        "portfolio_replay_policy": {
            "enabled_for_equity_options_sleeve": bool(include_equity),
            "time_major_candidate_selection": bool(include_equity),
            "max_positions": portfolio_max_positions,
            "default_target_allocation_fraction": portfolio_default_target_allocation_fraction,
            "target_allocation_fraction_role": "model_output_target_allocation_fraction_times_total_budget_not_single_position_cap",
            "default_fraction_role": "fallback_only_when_model_output_target_allocation_fraction_is_missing",
            "switch_minimum_rank_score_delta": portfolio_switch_minimum_rank_score_delta,
            "m05_trigger_policy": "ranked_m04_equity_intents_use_point_in_time_m05_selected_contract_cost_for_affordability",
            "position_sizing_policy": "rank_ordered_best_first_no_fixed_top_n_minimum_notional_floor_option_contract_round_up",
            "ranking_policy": {
                "rank_field": "diagnostic_rank_score",
                "role": "cross_target_ordering_for_replay_capital_feasibility",
                "formula": "positive(alpha_score-min_alpha) * positive(trade_intensity-min_trade_intensity) * positive(expected_return_score) * positive(action_direction_score)",
            },
        },
        "portfolio_selection_summary": portfolio_selection_summary,
        "candidate_model_ref": candidate_model_ref,
        "after_cost_alpha_model_ref": after_cost_alpha_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "replay_route_ref": EXECUTION_REPLAY_ROUTE_REF,
        "runtime_artifact_policy": {
            "component_output_contract_owner": "trading-execution",
            "component_output_contracts": list(RUNTIME_COMPONENT_OUTPUT_CONTRACTS),
            "execution_mode": "replay",
            "evaluation_decision_rows_role": "settlement_view_over_component_outputs",
            "replay_specific_component_contracts_allowed": False,
        },
        "candidate_fold_id": str(manifest.get("candidate_fold_id") or manifest.get("fold_id") or ""),
        "pre_replay_target_refs": sorted(_string_set(manifest.get("pre_replay_target_refs"))),
        "dataset_root": str(dataset_root),
        "dataset_manifest_ref": str(dataset_root / "dataset_manifest.json"),
        "replay_freeze_receipt_ref": None if replay_month else str(freeze_receipt_path),
        "replay_month": replay_month,
        "decision_rows_ref": str(decision_rows_path),
        "progress_ref": str(progress_path),
        "entry_threshold_calibration_ref": str(entry_calibration.path),
        "entry_threshold_calibration_status": entry_calibration.artifact["calibration_status"],
        "entry_thresholds": entry_calibration.artifact["selected_thresholds"],
        "decision_row_count": len(decision_rows),
        "completed_replay_month_count": len(progress_rows),
        "target_refs": sorted(bars_by_target),
        "asset_class_counts": _asset_class_counts(bars_by_target),
        "candidate_handoff_table_ref": (
            None
            if (
                not resolved_candidate_handoff_database_url
                or candidate_handoff["source"]
                in {
                    "explicit_candidate_symbols_override",
                    "fixed_current_snapshot_historical_candidate_universe",
                    "layer_02_target_candidate_handoff",
                }
            )
            else f"{candidate_handoff_schema}.{candidate_handoff_table}"
        ),
        "candidate_handoff_artifact_ref": candidate_handoff.get("artifact_ref"),
        "candidate_handoff_status": candidate_handoff["status"],
        "candidate_handoff_source": candidate_handoff["source"],
        "candidate_handoff_row_count": candidate_handoff["row_count"],
        "candidate_handoff_symbol_count": len(candidate_handoff["candidate_symbols"]),
        "candidate_handoff_symbols": list(candidate_handoff["candidate_symbols"]),
        "candidate_handoff_excluded_no_historical_bar_symbols": list(
            candidate_handoff.get("excluded_no_historical_bar_symbols") or []
        ),
        "option_feature_table_ref": None if not resolved_option_feature_database_url else f"{option_feature_schema}.{option_feature_table}",
        "option_feature_requirement_policy": _option_feature_requirement_policy(candidate_handoff),
        "option_feature_snapshot_count": len(option_candidates_by_underlying_time),
        "option_feature_candidate_count": sum(len(rows) for rows in option_candidates_by_underlying_time.values()),
        "option_contract_path_table_ref": None if not resolved_option_feature_database_url else f"{option_feature_schema}.{option_contract_path_table}",
        "option_contract_path_symbol_count": len(option_contract_paths_by_symbol),
        "option_contract_path_bar_count": sum(len(rows) for rows in option_contract_paths_by_symbol.values()),
        "option_replay_coverage": option_replay_coverage,
        "replay_time_pointer_policy": _replay_time_pointer_policy(),
        "market_date_count": len(market_dates),
        "generated_at_utc": generated_at,
        "validation_status": "passed",
        "side_effects": {
            "provider_calls_performed": 0,
            "broker_calls_performed": 0,
            "broker_mutation_performed": False,
            "account_mutation_performed": False,
            "model_training_performed": False,
            "active_model_config_written": False,
        },
        "notes": [
            "candidate-policy replay over frozen base context and gated on-demand candidate inputs",
            "C01-C07 component artifacts share live execution output contracts; evaluation_replay_decision_row is a settlement view",
            "each replay decision has an explicit replay_time_pointer; decision inputs after that pointer are invalid",
            "equity/options account requires point-in-time M05 option features at each replay decision timestamp",
            "equity/options replay is time-major and finite-capital: ranked M04 intents may use point-in-time M05 selected-contract cost for affordability before C05 order intent construction",
            "listed option decisions use M05 selected-contract paths when available; missing selected-contract paths are data-coverage diagnostics and not executable fills",
            "initial capital is replay-local simulated budget and never broker/account state",
            "this run emits settlement-ready decision rows but is not a promotion eligibility decision",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_jsonl(progress_path, progress_rows)
    return ReplayExecutionResult(
        receipt_path=receipt_path,
        decision_rows_path=decision_rows_path,
        progress_path=progress_path,
        receipt=receipt,
    )


def build_candidate_policy_portfolio_trace_audit(
    *,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    output_dir: Path | None = None,
    run_id: str | None = None,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any] | None,
    after_cost_alpha_model_ref: str | None = None,
    replay_contract_ref: str = "trading-evaluation/replays/promotion_replay_candidate_policy.json",
    generated_at_utc: str | None = None,
    calibration_window_month_count: int = DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT,
    calibration_max_decision_rows: int | None = None,
    include_crypto: bool = True,
    include_equity: bool = True,
    equity_source_root: Path = EQUITY_SOURCE_ROOT,
    equity_symbols: Sequence[str] | None = None,
    replay_month: str | None = None,
    candidate_handoff_database_url: str | None = None,
    candidate_handoff_schema: str = "trading_data",
    candidate_handoff_table: str = "model_02_sector_context_data_acquisition",
    candidate_universe_path: Path | None = None,
    initial_capital_usd: float = DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
    max_trace_timestamps: int | None = 20,
    max_positions: int = DEFAULT_PORTFOLIO_MAX_POSITIONS,
    default_target_allocation_fraction: float = DEFAULT_TARGET_ALLOCATION_FRACTION,
    switch_minimum_rank_score_delta: float = 0.05,
) -> PortfolioTraceAuditResult:
    """Trace how many M04 option-intent signals survive a finite-capital portfolio screen.

    This is a diagnostic audit. It reads the same frozen bars and model layers as
    candidate replay, but it does not load M05 option candidates, call providers,
    produce replay decision rows, activate models, or mutate account state.
    """

    candidate_model_ref = _require_candidate_model_ref(candidate_model_ref)
    if after_cost_alpha_model is None:
        raise ValueError("after_cost_alpha_model is required for portfolio trace audit Layer 5 inference")
    _validate_after_cost_alpha_model_for_replay(after_cost_alpha_model)
    initial_capital_usd = _validated_initial_capital_usd(initial_capital_usd)
    if max_positions < 0:
        raise ValueError("max_positions must be zero for unbounded or a positive integer")
    if default_target_allocation_fraction <= 0.0 or default_target_allocation_fraction > 1.0:
        raise ValueError("default_target_allocation_fraction must be in (0, 1]")
    if switch_minimum_rank_score_delta < 0.0:
        raise ValueError("switch_minimum_rank_score_delta must be non-negative")
    if max_trace_timestamps is not None and max_trace_timestamps <= 0:
        raise ValueError("max_trace_timestamps must be a positive integer when provided")

    manifest = _load_json(dataset_root / "dataset_manifest.json")
    freeze_receipt_path = dataset_root / "replay_freeze_receipt.json"
    freeze_receipt: dict[str, Any] | None = None
    plan_path = Path(str(manifest["feed_acquisition_plan_ref"]))
    if replay_month:
        _validate_replay_month_coverage(plan_path=plan_path, replay_month=replay_month)
    else:
        freeze_receipt = _load_json(freeze_receipt_path)
        _validate_frozen_dataset(manifest, freeze_receipt)

    candidate_handoff = _candidate_handoff_for_replay(
        database_url=candidate_handoff_database_url,
        schema=candidate_handoff_schema,
        table=candidate_handoff_table,
        candidate_universe_path=_resolved_candidate_universe_path(
            dataset_root=dataset_root,
            candidate_universe_path=candidate_universe_path,
        ),
        explicit_equity_symbols=equity_symbols,
        include_equity=include_equity,
        replay_month=replay_month,
    )
    generated_at = generated_at_utc or _now_utc()
    run_id = run_id or f"candidate_policy_portfolio_trace_audit_{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    output_dir = output_dir or dataset_root / "portfolio_trace_audits" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "portfolio_trace_audit_summary.json"
    trace_rows_path = output_dir / "portfolio_trace_rows.jsonl"
    calibration_path = output_dir / "entry_threshold_calibration.json"

    bars_by_target = _load_candidate_policy_bars(
        plan_path=plan_path,
        include_crypto=include_crypto,
        include_equity=include_equity,
        equity_source_root=equity_source_root,
        equity_symbols=candidate_handoff["candidate_symbols"],
        replay_month=replay_month,
    )
    if not bars_by_target:
        raise ValueError("candidate-policy portfolio trace audit found no materialized market bars")
    candidate_handoff = _prune_fixed_candidate_handoff_no_history_symbols(
        candidate_handoff=candidate_handoff,
        bars_by_target=bars_by_target,
        equity_source_root=equity_source_root,
        replay_month=replay_month,
    )
    _validate_equity_candidate_bar_coverage(
        include_equity=include_equity,
        explicit_equity_symbols=equity_symbols,
        candidate_handoff=candidate_handoff,
        bars_by_target=bars_by_target,
    )
    entry_calibration = _build_entry_calibration(
        bars_by_target=bars_by_target,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        replay_contract_ref=replay_contract_ref,
        generated_at_utc=generated_at,
        output_path=calibration_path,
        validation_month_count=calibration_window_month_count,
        max_decision_rows=calibration_max_decision_rows,
    )
    trace_rows, trace_summary = _build_candidate_policy_portfolio_trace_rows(
        bars_by_target=bars_by_target,
        run_id=run_id,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        replay_contract_ref=replay_contract_ref,
        entry_calibration=entry_calibration,
        initial_capital_usd=initial_capital_usd,
        max_trace_timestamps=max_trace_timestamps,
        max_positions=max_positions,
        default_target_allocation_fraction=default_target_allocation_fraction,
        switch_minimum_rank_score_delta=switch_minimum_rank_score_delta,
    )
    _write_jsonl(trace_rows_path, trace_rows)

    independent_count = int(trace_summary["independent_m05_signal_count"])
    avoided_count = int(trace_summary["avoided_m05_request_count"])
    summary = {
        "contract_type": PORTFOLIO_TRACE_AUDIT_CONTRACT,
        "replay_execution_run_id": run_id,
        "audit_scope": "finite_capital_m04_to_m05_trigger_trace",
        "candidate_model_ref": candidate_model_ref,
        "after_cost_alpha_model_ref": after_cost_alpha_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "dataset_root": str(dataset_root),
        "dataset_manifest_ref": str(dataset_root / "dataset_manifest.json"),
        "replay_freeze_receipt_ref": None if replay_month else str(freeze_receipt_path),
        "replay_month": replay_month,
        "trace_rows_ref": str(trace_rows_path),
        "entry_threshold_calibration_ref": str(entry_calibration.path),
        "entry_threshold_calibration_status": entry_calibration.artifact["calibration_status"],
        "entry_thresholds": entry_calibration.artifact["selected_thresholds"],
        "initial_capital_usd": initial_capital_usd,
        "initial_capital": {
            "amount": initial_capital_usd,
            "currency": REPLAY_INITIAL_CAPITAL_CURRENCY,
            "role": "portfolio_trace_audit_cash_budget",
            "broker_or_account_state": False,
        },
        "max_positions": max_positions,
        "default_target_allocation_fraction": default_target_allocation_fraction,
        "switch_minimum_rank_score_delta": switch_minimum_rank_score_delta,
        "max_trace_timestamps": max_trace_timestamps,
        "timestamp_count": trace_summary["timestamp_count"],
        "candidate_count": trace_summary["candidate_count"],
        "m04_trade_intent_count": trace_summary["m04_trade_intent_count"],
        "independent_m05_signal_count": independent_count,
        "capital_selected_m05_count": trace_summary["capital_selected_m05_count"],
        "avoided_m05_request_count": avoided_count,
        "m05_request_avoidance_ratio": avoided_count / independent_count if independent_count else 0.0,
        "candidate_handoff_status": candidate_handoff["status"],
        "candidate_handoff_source": candidate_handoff["source"],
        "candidate_handoff_row_count": candidate_handoff["row_count"],
        "candidate_handoff_symbol_count": len(candidate_handoff["candidate_symbols"]),
        "candidate_handoff_symbols": list(candidate_handoff["candidate_symbols"]),
        "candidate_handoff_artifact_ref": candidate_handoff.get("artifact_ref"),
        "target_refs": sorted(bars_by_target),
        "asset_class_counts": _asset_class_counts(bars_by_target),
        "ranking_policy": {
            "rank_field": "diagnostic_rank_score",
            "role": "audit_only_cross_target_ordering_for_capital_feasibility",
            "formula": "positive(alpha_score-min_alpha) * positive(trade_intensity-min_trade_intensity) * positive(expected_return_score) * positive(action_direction_score)",
            "promotion_or_execution_contract": False,
        },
        "side_effects": {
            "provider_calls_performed": 0,
            "option_feature_database_reads_performed": 0,
            "broker_calls_performed": 0,
            "broker_mutation_performed": False,
            "account_mutation_performed": False,
            "model_training_performed": False,
            "active_model_config_written": False,
        },
        "generated_at_utc": generated_at,
        "validation_status": "passed",
        "notes": [
            "diagnostic-only time-major portfolio trace over frozen replay bars",
            "max_positions=0 means no fixed top-N position-count limit",
            "independent_m05_signal_count approximates current target-major replay option-expression demand",
            "capital_selected_m05_count approximates option-expression demand after a simple finite-capital portfolio screen",
            "this audit does not load M05 option candidates, call option providers, emit replay decision rows, or mutate broker/account state",
            "the allocator is intentionally simple and must not be treated as the final replay account simulator",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PortfolioTraceAuditResult(
        summary_path=summary_path,
        trace_rows_path=trace_rows_path,
        entry_calibration_path=entry_calibration.path,
        summary=summary,
    )


def _build_candidate_policy_portfolio_trace_rows(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    run_id: str,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    replay_contract_ref: str,
    entry_calibration: EntryCalibration,
    initial_capital_usd: float,
    max_trace_timestamps: int | None,
    max_positions: int,
    default_target_allocation_fraction: float,
    switch_minimum_rank_score_delta: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    market_universe_by_date = _market_universe_by_date(
        history_by_target=history_by_target,
        index_by_target_date=index_by_target_date,
    )
    candidates_by_time: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in sorted(history_by_target):
        target_rows = history_by_target[target]
        for index, bar in enumerate(target_rows[:-1]):
            candidates_by_time[_replay_time_pointer_for_bar(bar)].append(
                {
                    "target": target,
                    "index": index,
                    "bar": bar,
                }
            )
    timestamps = sorted(candidates_by_time, key=_timestamp_sort_key)
    if max_trace_timestamps is not None:
        timestamps = timestamps[:max_trace_timestamps]

    cash = initial_capital_usd
    position_budget = initial_capital_usd * default_target_allocation_fraction
    positions: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    summary = {
        "timestamp_count": 0,
        "candidate_count": 0,
        "m04_trade_intent_count": 0,
        "independent_m05_signal_count": 0,
        "capital_selected_m05_count": 0,
        "avoided_m05_request_count": 0,
    }

    for timestamp in timestamps:
        items = candidates_by_time[timestamp]
        cash_before = cash
        positions_before = sorted(positions)
        scored_candidates: list[dict[str, Any]] = []
        for item in items:
            target = str(item["target"])
            index = int(item["index"])
            bar = _as_mapping(item["bar"])
            date_text = str(bar["date"])
            target_rows = history_by_target[target]
            market_universe = market_universe_by_date.get(date_text, ())
            reference_price = float(bar["bar_close"])
            layer_outputs = _candidate_layer_outputs(
                target=target,
                target_rows=target_rows,
                index=index,
                market_universe=market_universe,
                reference_price=reference_price,
                candidate_model_ref=candidate_model_ref,
                after_cost_alpha_model=after_cost_alpha_model,
                entry_calibration=entry_calibration.artifact,
            )
            diagnostics = _portfolio_trace_candidate_diagnostics(
                target=target,
                timestamp=timestamp,
                reference_price=reference_price,
                layer_outputs=layer_outputs,
            )
            independent_m05_signal = str(bar.get("asset_class") or "") == "us_equity" and _option_expression_signal_required(
                layer_outputs
            )
            diagnostics["independent_m05_signal"] = independent_m05_signal
            if independent_m05_signal:
                scored_candidates.append(diagnostics)

        scored_candidates.sort(key=lambda row: (-float(row["diagnostic_rank_score"]), str(row["target_ref"])))
        selected_targets: list[str] = []
        closed_targets: list[str] = []
        for candidate in scored_candidates:
            target = str(candidate["target_ref"])
            if target in positions:
                positions[target]["last_rank_score"] = candidate["diagnostic_rank_score"]
                positions[target]["last_price"] = candidate["reference_price"]
                continue
            if _position_limit_allows_new_position(positions=positions, max_positions=max_positions) and cash > 0.0:
                notional = min(position_budget, cash)
                if notional <= 0.0:
                    continue
                positions[target] = _portfolio_trace_position(
                    candidate=candidate,
                    notional=notional,
                    opened_at=timestamp,
                )
                cash -= notional
                selected_targets.append(target)
                continue
            if max_positions == 0:
                continue
            if not positions:
                continue
            worst_target, worst_position = min(
                positions.items(),
                key=lambda item: (float(item[1].get("last_rank_score") or item[1].get("entry_rank_score") or 0.0), item[0]),
            )
            candidate_score = float(candidate["diagnostic_rank_score"])
            worst_score = float(worst_position.get("last_rank_score") or worst_position.get("entry_rank_score") or 0.0)
            if candidate_score - worst_score < switch_minimum_rank_score_delta:
                continue
            cash += _portfolio_trace_position_value(worst_position)
            closed_targets.append(worst_target)
            del positions[worst_target]
            notional = min(position_budget, cash)
            if notional <= 0.0:
                continue
            positions[target] = _portfolio_trace_position(candidate=candidate, notional=notional, opened_at=timestamp)
            cash -= notional
            selected_targets.append(target)

        independent_count = len(scored_candidates)
        selected_count = len(selected_targets)
        m04_trade_intent_count = sum(1 for candidate in scored_candidates if candidate["m04_trade_intent"])
        avoided_count = max(0, independent_count - selected_count)
        row = {
            "contract_type": PORTFOLIO_TRACE_AUDIT_ROW_CONTRACT,
            "replay_execution_run_id": run_id,
            "replay_contract_ref": replay_contract_ref,
            "timestamp": timestamp,
            "cash_before": cash_before,
            "cash_after": cash,
            "open_position_count_before": len(positions_before),
            "open_position_count_after": len(positions),
            "position_targets_before": positions_before,
            "position_targets_after": sorted(positions),
            "candidate_count": len(items),
            "m04_trade_intent_count": m04_trade_intent_count,
            "independent_m05_signal_count": independent_count,
            "capital_selected_m05_count": selected_count,
            "avoided_m05_request_count": avoided_count,
            "selected_targets": selected_targets,
            "closed_targets": closed_targets,
            "top_independent_m05_candidates": scored_candidates[:10],
            "top_capital_rejected_targets": [candidate["target_ref"] for candidate in scored_candidates if candidate["target_ref"] not in selected_targets][:10],
        }
        rows.append(row)
        summary["timestamp_count"] += 1
        summary["candidate_count"] += len(items)
        summary["m04_trade_intent_count"] += m04_trade_intent_count
        summary["independent_m05_signal_count"] += independent_count
        summary["capital_selected_m05_count"] += selected_count
        summary["avoided_m05_request_count"] += avoided_count
    return rows, summary


def _portfolio_trace_candidate_diagnostics(
    *,
    target: str,
    timestamp: str,
    reference_price: float,
    layer_outputs: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics = _as_mapping(layer_outputs.get("model_layer_diagnostics"))
    thresholds = _as_mapping(diagnostics.get("entry_thresholds"))
    alpha_diagnostics = _as_mapping(diagnostics.get("model_05_alpha_confidence"))
    layer4 = _as_mapping(diagnostics.get("model_04_unified_decision"))
    dominant = _as_mapping(layer4.get("dominant_horizon_scores"))
    plan = _as_mapping(layer_outputs.get("direct_underlying_intent"))
    alpha_score = _safe_float(layer_outputs.get("prediction_score")) or 0.0
    trade_intensity = _safe_float(dominant.get("trade_intensity_score")) or _safe_float(plan.get("trade_intensity_score")) or 0.0
    action_direction = _safe_float(dominant.get("action_direction_score")) or 0.0
    expected_return = _safe_float(dominant.get("expected_return_score")) or 0.0
    minimum_alpha = _safe_float(thresholds.get("minimum_entry_alpha_confidence")) or DEFAULT_ENTRY_ALPHA_THRESHOLD
    minimum_trade_intensity = _safe_float(dominant.get("minimum_trade_intensity")) or _safe_float(
        thresholds.get("minimum_trade_intensity")
    ) or DEFAULT_MINIMUM_TRADE_INTENSITY
    action_type = str(plan.get("underlying_action_type") or plan.get("planned_underlying_action_type") or "").lower()
    action_side = str(plan.get("action_side") or "").lower()
    rank_score = (
        max(0.0, alpha_score - minimum_alpha)
        * max(0.0, trade_intensity - minimum_trade_intensity)
        * max(0.0, expected_return)
        * max(0.0, action_direction)
    )
    return {
        "target_ref": target,
        "timestamp": timestamp,
        "reference_price": reference_price,
        "m04_trade_intent": action_type not in {"", "no_trade"} and action_side != "none",
        "underlying_action_type": action_type,
        "action_side": action_side,
        "entry_style": str(plan.get("entry_style") or _as_mapping(plan.get("handoff_to_model_05")).get("entry_price_assumption") or ""),
        "alpha_score": alpha_score,
        "alpha_gate_status": str(alpha_diagnostics.get("alpha_gate_status") or ""),
        "minimum_entry_alpha_confidence": minimum_alpha,
        "trade_intensity_score": trade_intensity,
        "minimum_trade_intensity": minimum_trade_intensity,
        "action_direction_score": action_direction,
        "expected_return_score": expected_return,
        "diagnostic_rank_score": rank_score,
    }


def _portfolio_trace_position(
    *,
    candidate: Mapping[str, Any],
    notional: float,
    quantity: float | None = None,
    unit_cost: float | None = None,
    opened_at: str,
) -> dict[str, Any]:
    price = float(candidate["reference_price"])
    position_quantity = quantity if quantity is not None else (notional / price if price > 0.0 else 0.0)
    return {
        "target_ref": str(candidate["target_ref"]),
        "opened_at": opened_at,
        "entry_price": price,
        "last_price": price,
        "quantity": position_quantity,
        "unit_cost": unit_cost,
        "notional": notional,
        "entry_rank_score": float(candidate["diagnostic_rank_score"]),
        "last_rank_score": float(candidate["diagnostic_rank_score"]),
    }


def _portfolio_trace_position_value(position: Mapping[str, Any]) -> float:
    notional = _safe_float(position.get("notional")) or 0.0
    unit_cost = _safe_float(position.get("unit_cost"))
    quantity = _safe_float(position.get("quantity")) or 0.0
    if unit_cost is not None and unit_cost > 0.0 and quantity > 0.0:
        return unit_cost * quantity
    last_price = _safe_float(position.get("last_price")) or _safe_float(position.get("entry_price")) or 0.0
    value = quantity * last_price
    if value > 0.0 and value >= notional * 0.5:
        return value
    return notional


def _position_limit_allows_new_position(*, positions: Mapping[str, Any], max_positions: int) -> bool:
    return max_positions == 0 or len(positions) < max_positions


def _ranked_candidate_option_expression_plan(
    *,
    candidate: Mapping[str, Any],
    candidate_model_ref: str,
    option_candidates_by_underlying_time: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> Mapping[str, Any] | None:
    target = str(candidate["target_ref"]).upper()
    timestamp = str(candidate["timestamp"])
    option_candidates = option_candidates_by_underlying_time.get((target, timestamp), ())
    if not option_candidates:
        return None
    return _option_expression_plan_for_bar(
        bar=_as_mapping(candidate["bar"]),
        candidate_model_ref=candidate_model_ref,
        timestamp=timestamp,
        layer_outputs=_as_mapping(candidate["layer_outputs"]),
        option_candidates=option_candidates,
    )


def _target_allocation_context(
    *,
    layer_outputs: Mapping[str, Any],
    total_portfolio_notional_usd: float,
    default_target_allocation_fraction: float,
) -> dict[str, Any]:
    fraction, source = _model_output_target_allocation_fraction(layer_outputs)
    if fraction is None:
        fraction = default_target_allocation_fraction
        source = "portfolio_default_target_allocation_fraction"
    notional = max(0.0, total_portfolio_notional_usd * fraction)
    return {
        "target_allocation_fraction": float(fraction),
        "target_allocation_fraction_source": source,
        "total_portfolio_notional_usd": float(total_portfolio_notional_usd),
        "target_allocation_notional_usd": float(notional),
    }


def _model_output_target_allocation_fraction(layer_outputs: Mapping[str, Any]) -> tuple[float | None, str | None]:
    unified = _as_mapping(layer_outputs.get("unified_decision_vector"))
    direct_intent = _as_mapping(layer_outputs.get("direct_underlying_intent") or unified.get("direct_underlying_intent"))
    handoff = _as_mapping(direct_intent.get("handoff_to_model_05"))
    sources = (
        ("model_05_handoff.target_allocation_fraction", handoff.get("target_allocation_fraction")),
        ("direct_underlying_intent.target_allocation_fraction", direct_intent.get("target_allocation_fraction")),
        ("unified_decision_vector.4_resolved_target_allocation_fraction", unified.get("4_resolved_target_allocation_fraction")),
        ("unified_decision_vector.target_allocation_fraction", unified.get("target_allocation_fraction")),
        ("unified_decision_vector.4_target_allocation_fraction_1D", unified.get("4_target_allocation_fraction_1D")),
        ("unified_decision_vector.4_target_allocation_fraction_1W", unified.get("4_target_allocation_fraction_1W")),
    )
    for source, raw in sources:
        fraction = _safe_float(raw)
        if fraction is not None and 0.0 < fraction <= 1.0:
            return fraction, source
    return None, None


def _candidate_position_allocation(
    *,
    cash: float,
    minimum_position_notional_usd: float,
    option_expression_plan: Mapping[str, Any] | None,
    reference_price: float,
) -> dict[str, float] | None:
    if cash <= 0.0:
        return None
    selected_contract = _as_mapping(_as_mapping(option_expression_plan).get("selected_contract"))
    unit_cost = _selected_option_contract_unit_cost(selected_contract)
    if unit_cost is None:
        unit_cost = reference_price if reference_price > 0.0 else None
    if unit_cost is None or unit_cost <= 0.0:
        return None
    if selected_contract:
        quantity = max(1, math.ceil(minimum_position_notional_usd / unit_cost))
        notional = unit_cost * quantity
        if notional > cash + 1e-9:
            return None
        return {
            "quantity": float(quantity),
            "unit_cost": float(unit_cost),
            "notional": float(notional),
        }
    notional = min(max(minimum_position_notional_usd, 0.0), cash)
    if notional <= 0.0:
        return None
    return {
        "quantity": notional / unit_cost,
        "unit_cost": float(unit_cost),
        "notional": float(notional),
    }


def _selected_option_contract_unit_cost(selected_contract: Mapping[str, Any]) -> float | None:
    if not selected_contract:
        return None
    explicit_cost = _safe_float(
        selected_contract.get("estimated_contract_cost_usd")
        or selected_contract.get("contract_cost_usd")
        or selected_contract.get("notional_cost_usd")
    )
    if explicit_cost is not None and explicit_cost > 0.0:
        return explicit_cost
    mid_price = _safe_float(
        selected_contract.get("mid_price")
        or selected_contract.get("mark_price")
        or selected_contract.get("ask_price")
        or selected_contract.get("last_price")
    )
    if mid_price is None or mid_price <= 0.0:
        return None
    multiplier = _safe_float(selected_contract.get("contract_multiplier") or selected_contract.get("multiplier"))
    if multiplier is None or multiplier <= 0.0:
        multiplier = US_OPTION_CONTRACT_MULTIPLIER
    return mid_price * multiplier


def _validate_portfolio_replay_policy(
    *,
    max_positions: int,
    default_target_allocation_fraction: float,
    switch_minimum_rank_score_delta: float,
) -> None:
    if max_positions < 0:
        raise ValueError("portfolio max_positions must be zero for unbounded or a positive integer")
    if default_target_allocation_fraction <= 0.0 or default_target_allocation_fraction > 1.0:
        raise ValueError("portfolio default_target_allocation_fraction must be in (0, 1]")
    if switch_minimum_rank_score_delta < 0.0:
        raise ValueError("portfolio switch_minimum_rank_score_delta must be non-negative")


def _select_candidate_policy_portfolio_replay_keys(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    entry_calibration: EntryCalibration,
    option_candidates_by_underlying_time: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    initial_capital_usd: float,
    max_positions: int,
    default_target_allocation_fraction: float,
    switch_minimum_rank_score_delta: float,
) -> tuple[
    set[tuple[str, int]],
    dict[tuple[str, int], dict[str, Any]],
    dict[tuple[str, int], Mapping[str, Any] | None],
    dict[str, Any],
]:
    _validate_portfolio_replay_policy(
        max_positions=max_positions,
        default_target_allocation_fraction=default_target_allocation_fraction,
        switch_minimum_rank_score_delta=switch_minimum_rank_score_delta,
    )
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    market_universe_by_date = _market_universe_by_date(
        history_by_target=history_by_target,
        index_by_target_date=index_by_target_date,
    )
    candidates_by_time: dict[str, list[tuple[str, int, Mapping[str, Any]]]] = defaultdict(list)
    for target in sorted(history_by_target):
        target_rows = history_by_target[target]
        for index, bar in enumerate(target_rows[:-1]):
            if str(bar.get("asset_class") or "") != "us_equity":
                continue
            candidates_by_time[_replay_time_pointer_for_bar(bar)].append((target, index, bar))

    cash = initial_capital_usd
    positions: dict[str, dict[str, Any]] = {}
    selected_keys: set[tuple[str, int]] = set()
    layer_outputs_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    option_expression_plans_by_key: dict[tuple[str, int], Mapping[str, Any] | None] = {}
    summary = {
        "timestamp_count": 0,
        "candidate_count": 0,
        "m04_trade_intent_count": 0,
        "independent_m05_signal_count": 0,
        "capital_selected_m05_count": 0,
        "avoided_m05_request_count": 0,
        "default_target_allocation_fraction": default_target_allocation_fraction,
        "target_allocation_fraction_role": "model_output_target_allocation_fraction_times_total_budget_not_single_position_cap",
        "max_positions": max_positions,
        "max_positions_role": "unbounded_when_zero" if max_positions == 0 else "optional_position_count_limit",
        "final_cash": initial_capital_usd,
        "final_position_count": 0,
        "final_position_targets": [],
    }

    for timestamp in sorted(candidates_by_time, key=_timestamp_sort_key):
        timestamp_candidates: list[dict[str, Any]] = []
        for target, index, bar in candidates_by_time[timestamp]:
            target_rows = history_by_target[target]
            date_text = str(bar["date"])
            reference_price = float(bar["bar_close"])
            key = (target, index)
            layer_outputs = _candidate_layer_outputs(
                target=target,
                target_rows=target_rows,
                index=index,
                market_universe=market_universe_by_date.get(date_text, ()),
                reference_price=reference_price,
                candidate_model_ref=candidate_model_ref,
                after_cost_alpha_model=after_cost_alpha_model,
                entry_calibration=entry_calibration.artifact,
            )
            layer_outputs_by_key[key] = layer_outputs
            diagnostics = _portfolio_trace_candidate_diagnostics(
                target=target,
                timestamp=timestamp,
                reference_price=reference_price,
                layer_outputs=layer_outputs,
            )
            summary["candidate_count"] += 1
            if diagnostics["m04_trade_intent"]:
                summary["m04_trade_intent_count"] += 1
            if _option_expression_signal_required(layer_outputs):
                diagnostics["key"] = key
                diagnostics["timestamp"] = _replay_time_pointer_for_bar(bar)
                diagnostics["bar"] = bar
                diagnostics["layer_outputs"] = layer_outputs
                timestamp_candidates.append(diagnostics)
                summary["independent_m05_signal_count"] += 1

        timestamp_candidates.sort(key=lambda row: (-float(row["diagnostic_rank_score"]), str(row["target_ref"])))
        selected_this_timestamp = 0
        for candidate in timestamp_candidates:
            target = str(candidate["target_ref"])
            if target in positions:
                positions[target]["last_rank_score"] = candidate["diagnostic_rank_score"]
                positions[target]["last_price"] = candidate["reference_price"]
                continue
            key = candidate["key"]
            if _position_limit_allows_new_position(positions=positions, max_positions=max_positions) and cash > 0.0:
                option_expression_plan = _ranked_candidate_option_expression_plan(
                    candidate=candidate,
                    candidate_model_ref=candidate_model_ref,
                    option_candidates_by_underlying_time=option_candidates_by_underlying_time,
                )
                option_expression_plans_by_key[key] = option_expression_plan
                allocation_context = _target_allocation_context(
                    layer_outputs=_as_mapping(candidate["layer_outputs"]),
                    total_portfolio_notional_usd=initial_capital_usd,
                    default_target_allocation_fraction=default_target_allocation_fraction,
                )
                allocation = _candidate_position_allocation(
                    cash=cash,
                    minimum_position_notional_usd=allocation_context["target_allocation_notional_usd"],
                    option_expression_plan=option_expression_plan,
                    reference_price=float(candidate["reference_price"]),
                )
                if allocation is None:
                    continue
                positions[target] = _portfolio_trace_position(
                    candidate=candidate,
                    notional=allocation["notional"],
                    quantity=allocation["quantity"],
                    unit_cost=allocation["unit_cost"],
                    opened_at=timestamp,
                )
                cash -= allocation["notional"]
                selected_keys.add(candidate["key"])
                selected_this_timestamp += 1
                continue
            if max_positions == 0:
                continue
            if not positions:
                continue
            worst_target, worst_position = min(
                positions.items(),
                key=lambda item: (float(item[1].get("last_rank_score") or item[1].get("entry_rank_score") or 0.0), item[0]),
            )
            candidate_score = float(candidate["diagnostic_rank_score"])
            worst_score = float(worst_position.get("last_rank_score") or worst_position.get("entry_rank_score") or 0.0)
            if candidate_score - worst_score < switch_minimum_rank_score_delta:
                continue
            option_expression_plan = _ranked_candidate_option_expression_plan(
                candidate=candidate,
                candidate_model_ref=candidate_model_ref,
                option_candidates_by_underlying_time=option_candidates_by_underlying_time,
            )
            option_expression_plans_by_key[key] = option_expression_plan
            prospective_cash = cash + _portfolio_trace_position_value(worst_position)
            allocation_context = _target_allocation_context(
                layer_outputs=_as_mapping(candidate["layer_outputs"]),
                total_portfolio_notional_usd=initial_capital_usd,
                default_target_allocation_fraction=default_target_allocation_fraction,
            )
            allocation = _candidate_position_allocation(
                cash=prospective_cash,
                minimum_position_notional_usd=allocation_context["target_allocation_notional_usd"],
                option_expression_plan=option_expression_plan,
                reference_price=float(candidate["reference_price"]),
            )
            if allocation is None:
                continue
            cash = prospective_cash
            del positions[worst_target]
            positions[target] = _portfolio_trace_position(
                candidate=candidate,
                notional=allocation["notional"],
                quantity=allocation["quantity"],
                unit_cost=allocation["unit_cost"],
                opened_at=timestamp,
            )
            cash -= allocation["notional"]
            selected_keys.add(candidate["key"])
            selected_this_timestamp += 1

        summary["timestamp_count"] += 1
        summary["capital_selected_m05_count"] += selected_this_timestamp
        summary["avoided_m05_request_count"] += max(0, len(timestamp_candidates) - selected_this_timestamp)

    summary["final_cash"] = round(cash, 6)
    summary["final_position_count"] = len(positions)
    summary["final_position_targets"] = sorted(positions)
    return selected_keys, layer_outputs_by_key, option_expression_plans_by_key, summary


def _require_candidate_model_ref(candidate_model_ref: str) -> str:
    text = str(candidate_model_ref or "").strip()
    if not text:
        raise ValueError("candidate_model_ref is required")
    if text in DISALLOWED_PLACEHOLDER_CANDIDATE_MODEL_REFS:
        raise ValueError("candidate_model_ref must point to a concrete model-group candidate, not the deterministic placeholder")
    return text


def _validated_initial_capital_usd(value: float) -> float:
    capital = float(value)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("initial_capital_usd must be a positive finite number")
    return capital


def _validate_after_cost_alpha_model_for_replay(after_cost_alpha_model: Mapping[str, Any]) -> None:
    artifacts = after_cost_alpha_model.get("artifacts_by_horizon")
    if isinstance(artifacts, Mapping):
        artifact_items = [(str(horizon), artifact) for horizon, artifact in artifacts.items()]
    else:
        horizon = str(after_cost_alpha_model.get("horizon") or "unknown")
        artifact_items = [(horizon, after_cost_alpha_model)]
    if not artifact_items:
        raise ValueError("degenerate_after_cost_alpha_artifact: artifact bundle contains no horizons")
    degenerate: list[str] = []
    for horizon, artifact in artifact_items:
        if not isinstance(artifact, Mapping) or _after_cost_artifact_is_degenerate(artifact):
            degenerate.append(horizon)
    if degenerate:
        raise ValueError(
            "degenerate_after_cost_alpha_artifact: "
            "Layer 5 after-cost alpha artifact has no usable LightGBM split structure for "
            + ", ".join(sorted(degenerate))
        )


def _after_cost_artifact_is_degenerate(artifact: Mapping[str, Any]) -> bool:
    model_text = str(artifact.get("booster_model") or "")
    if not model_text.strip():
        return True
    saw_tree = False
    saw_split = False
    for line in model_text.splitlines():
        if line.startswith("Tree="):
            saw_tree = True
        elif line.startswith("num_leaves="):
            try:
                if int(line.split("=", 1)[1].strip()) > 1:
                    saw_split = True
            except ValueError:
                continue
        elif line.startswith("split_feature=") and line.split("=", 1)[1].strip():
            saw_split = True
    return not (saw_tree and saw_split)


def _build_replay_progress_rows(
    *,
    decision_rows: Sequence[Mapping[str, Any]],
    run_id: str,
    generated_at_utc: str,
    receipt_path: Path,
    decision_rows_path: Path,
    initial_capital_usd: float,
) -> list[dict[str, Any]]:
    rows_by_month: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in decision_rows:
        timestamp = str(row.get("timestamp") or "")
        replay_month = timestamp[:7]
        if len(replay_month) == 7 and replay_month[4] == "-":
            rows_by_month[replay_month].append(row)
    progress_rows: list[dict[str, Any]] = []
    for replay_month in sorted(rows_by_month):
        month_rows = rows_by_month[replay_month]
        progress_rows.append(
            {
                "contract_type": REPLAY_PROGRESS_CONTRACT,
                "stage_id": "model_group.replay",
                "status": "completed",
                "replay_status": "completed",
                "month": replay_month,
                "replay_month": replay_month,
                "replay_execution_run_id": run_id,
                "execution_scope": "candidate_policy_replay_materialized_market_data",
                "decision_row_count": len(month_rows),
                "target_refs": sorted({str(row.get("target_ref") or "") for row in month_rows if row.get("target_ref")}),
                "receipt_ref": str(receipt_path),
                "decision_rows_ref": str(decision_rows_path),
                "initial_capital_usd": initial_capital_usd,
                "generated_at_utc": generated_at_utc,
            }
        )
    return progress_rows


def _build_entry_calibration(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    replay_contract_ref: str,
    generated_at_utc: str,
    output_path: Path,
    validation_month_count: int,
    max_decision_rows: int | None,
) -> EntryCalibration:
    validation_months = _entry_calibration_validation_months(
        bars_by_target=bars_by_target,
        validation_month_count=validation_month_count,
    )
    observations = _entry_calibration_observations(
        bars_by_target=bars_by_target,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        max_decision_rows=max_decision_rows,
        replay_months=validation_months,
    )
    observed_validation_months = sorted({str(row["replay_month"]) for row in observations})
    selected = _select_entry_thresholds(observations)
    artifact = {
        "contract_type": ENTRY_THRESHOLD_CALIBRATION_CONTRACT,
        "candidate_model_ref": candidate_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "generated_at_utc": generated_at_utc,
        "calibration_method": "current_model_05_alpha_confidence_and_model_04_trade_intensity_validation_selection",
        "observation_scope": "validation_months_only",
        "validation_months": observed_validation_months,
        "candidate_validation_months": list(validation_months),
        "validation_observation_count": len(observations),
        "total_observation_count": len(observations),
        "selected_thresholds": selected["thresholds"],
        "selected_metrics": selected["metrics"],
        "calibration_diagnostics": selected["diagnostics"],
        "calibration_status": selected["status"],
        "candidate_threshold_count": selected["candidate_threshold_count"],
        "notes": [
            "M05 after-cost alpha confidence uses the normalized entry boundary: 0.5 is neutral, above 0.5 is positive edge",
            "validation selects M05 alpha confidence and M04 trade intensity thresholds from frozen replay observations",
            "selection uses M05 alpha confidence, M04 trade intensity, positive expected-return direction, and next-bar validation utility after replay costs",
            "post-replay attribution is not used for same-run entry decisions",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return EntryCalibration(artifact=artifact, path=output_path)


def _entry_calibration_validation_months(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    validation_month_count: int,
) -> tuple[str, ...]:
    months = sorted(
        {
            str(row.get("timestamp") or row.get("date") or "")[:7]
            for rows in bars_by_target.values()
            for row in list(rows)[:-1]
            if str(row.get("timestamp") or row.get("date") or "")[:7]
        }
    )
    return tuple(months[: max(validation_month_count, 1)])


def _entry_calibration_observations(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    max_decision_rows: int | None,
    replay_months: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    replay_month_filter = set(replay_months or ())
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    market_universe_by_date = _market_universe_by_date(
        history_by_target=history_by_target,
        index_by_target_date=index_by_target_date,
    )
    for target in sorted(history_by_target):
        target_rows = history_by_target[target]
        for index, bar in enumerate(target_rows[:-1]):
            replay_month = str(bar["timestamp"])[:7]
            if replay_month_filter and replay_month not in replay_month_filter:
                continue
            if max_decision_rows is not None and len(observations) >= max_decision_rows:
                return observations
            next_bar = target_rows[index + 1]
            reference_price = float(bar["bar_close"])
            layer_outputs = _candidate_layer_outputs(
                target=target,
                target_rows=target_rows,
                index=index,
                market_universe=market_universe_by_date.get(str(bar["date"]), ()),
                reference_price=reference_price,
                candidate_model_ref=candidate_model_ref,
                after_cost_alpha_model=after_cost_alpha_model,
                entry_calibration=_raw_entry_calibration(),
            )
            diagnostics = layer_outputs["model_layer_diagnostics"]
            layer4 = diagnostics["model_04_unified_decision"]
            dominant = layer4["dominant_horizon_scores"]
            gross_return = (float(next_bar["bar_close"]) - reference_price) / reference_price
            observations.append(
                {
                    "target_ref": target,
                    "timestamp": bar["timestamp"],
                    "replay_month": replay_month,
                    "alpha_confidence": float(layer_outputs["prediction_score"]),
                    "trade_intensity": float(dominant["trade_intensity_score"]),
                    "action_confidence": float(dominant["action_confidence_score"]),
                    "action_direction": float(dominant["action_direction_score"]),
                    "expected_return_score": float(dominant["expected_return_score"]),
                    "gross_return": gross_return,
                    "return_after_cost": gross_return - REPLAY_COST_PER_FILLED_DECISION,
                }
            )
    return observations


def _select_entry_thresholds(validation_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    diagnostics = _entry_calibration_diagnostics(validation_rows)
    if len(validation_rows) < MINIMUM_CALIBRATION_OBSERVATION_COUNT:
        return _fallback_entry_threshold_selection(
            status="fallback_insufficient_validation_observations",
            diagnostics=diagnostics,
        )
    if diagnostics["alpha_unique_value_count"] < MINIMUM_CALIBRATION_ALPHA_UNIQUE_VALUES or diagnostics["alpha_stdev"] < MINIMUM_CALIBRATION_ALPHA_STDEV:
        return _fallback_entry_threshold_selection(
            status="fallback_degenerate_validation_alpha_scores",
            diagnostics=diagnostics,
        )

    alpha_thresholds = [round(value / 100.0, 2) for value in range(int(MINIMUM_ENTRY_ALPHA_THRESHOLD * 100), 91, 5)]
    intensity_thresholds = [round(value / 1000.0, 3) for value in range(1, 31)]
    min_trade_count = max(MINIMUM_CALIBRATION_SELECTED_TRADE_COUNT, math.ceil(len(validation_rows) * 0.02))
    candidates: list[dict[str, Any]] = []
    for alpha_threshold in alpha_thresholds:
        for intensity_threshold in intensity_thresholds:
            selected = [
                row
                for row in validation_rows
                if float(row["alpha_confidence"]) >= alpha_threshold
                and float(row["trade_intensity"]) >= intensity_threshold
                and float(row["action_direction"]) > 0
                and float(row["expected_return_score"]) > 0
            ]
            if len(selected) < min_trade_count:
                continue
            returns = [float(row["return_after_cost"]) for row in selected]
            metrics = _threshold_metrics(returns)
            objective = metrics["average_return_after_cost"] * math.sqrt(len(returns)) - metrics["max_drawdown"] * 0.05
            candidates.append(
                {
                    "thresholds": {
                        "minimum_entry_alpha_confidence": alpha_threshold,
                        "minimum_trade_intensity": intensity_threshold,
                    },
                    "metrics": metrics,
                    "objective_score": objective,
                }
            )
    positive = [item for item in candidates if item["metrics"]["total_return_after_cost"] > 0 and item["metrics"]["average_return_after_cost"] > 0]
    if positive:
        selected = max(
            positive,
            key=lambda item: (
                item["objective_score"],
                item["metrics"]["trade_count"],
                -item["thresholds"]["minimum_entry_alpha_confidence"],
                -item["thresholds"]["minimum_trade_intensity"],
            ),
        )
        return {
            "status": "selected_positive_validation_threshold",
            "thresholds": selected["thresholds"],
            "metrics": selected["metrics"],
            "diagnostics": diagnostics,
            "candidate_threshold_count": len(candidates),
        }
    return _fallback_entry_threshold_selection(
        status="fallback_no_positive_validation_threshold_candidate" if candidates else "fallback_no_validation_threshold_candidate",
        diagnostics=diagnostics,
        candidate_threshold_count=len(candidates),
    )


def _entry_calibration_diagnostics(validation_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    alpha_scores = [float(row["alpha_confidence"]) for row in validation_rows]
    alpha_mean = sum(alpha_scores) / len(alpha_scores) if alpha_scores else 0.0
    alpha_stdev = (
        math.sqrt(sum((score - alpha_mean) ** 2 for score in alpha_scores) / len(alpha_scores))
        if alpha_scores
        else 0.0
    )
    alpha_positive_edge_rows = sum(1 for row in validation_rows if float(row["alpha_confidence"]) >= MINIMUM_ENTRY_ALPHA_THRESHOLD)
    action_candidate_rows = sum(
        1
        for row in validation_rows
        if float(row["action_direction"]) > 0
        and float(row["expected_return_score"]) > 0
        and float(row["trade_intensity"]) > 0
    )
    return {
        "minimum_required_observation_count": MINIMUM_CALIBRATION_OBSERVATION_COUNT,
        "minimum_required_selected_trade_count": MINIMUM_CALIBRATION_SELECTED_TRADE_COUNT,
        "minimum_entry_alpha_threshold": MINIMUM_ENTRY_ALPHA_THRESHOLD,
        "observation_count": len(validation_rows),
        "alpha_unique_value_count": len({round(score, 6) for score in alpha_scores}),
        "alpha_stdev": round(alpha_stdev, 8),
        "alpha_min": round(min(alpha_scores), 8) if alpha_scores else None,
        "alpha_max": round(max(alpha_scores), 8) if alpha_scores else None,
        "alpha_positive_edge_row_count": alpha_positive_edge_rows,
        "action_candidate_row_count": action_candidate_rows,
    }


def _fallback_entry_threshold_selection(
    *,
    status: str,
    diagnostics: Mapping[str, Any],
    candidate_threshold_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "thresholds": {
            "minimum_entry_alpha_confidence": DEFAULT_ENTRY_ALPHA_THRESHOLD,
            "minimum_trade_intensity": DEFAULT_MINIMUM_TRADE_INTENSITY,
        },
        "metrics": {
            "trade_count": 0,
            "win_rate_after_cost": 0.0,
            "average_return_after_cost": 0.0,
            "total_return_after_cost": 0.0,
            "max_drawdown": 0.0,
        },
        "diagnostics": dict(diagnostics),
        "candidate_threshold_count": candidate_threshold_count,
    }


def _threshold_metrics(returns: Sequence[float]) -> dict[str, Any]:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return {
        "trade_count": len(returns),
        "win_rate_after_cost": sum(1 for value in returns if value > 0) / len(returns) if returns else 0.0,
        "average_return_after_cost": sum(returns) / len(returns) if returns else 0.0,
        "total_return_after_cost": sum(returns),
        "max_drawdown": max_drawdown,
    }


def _build_candidate_policy_decision_rows(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    market_dates: Sequence[str],
    run_id: str,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    replay_contract_ref: str,
    max_decision_rows: int | None,
    entry_calibration: EntryCalibration,
    option_candidates_by_underlying_time: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    option_contract_paths_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    option_feature_requirements_path: Path | None = None,
    allow_option_feature_requirements: bool = True,
    selected_equity_replay_keys: set[tuple[str, int]] | None = None,
    precomputed_layer_outputs: Mapping[tuple[str, int], Mapping[str, Any]] | None = None,
    precomputed_option_expression_plans: Mapping[tuple[str, int], Mapping[str, Any] | None] | None = None,
    total_portfolio_notional_usd: float = DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
    default_target_allocation_fraction: float = DEFAULT_TARGET_ALLOCATION_FRACTION,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing_option_feature_requirements: list[dict[str, str]] = []
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    market_universe_by_date = _market_universe_by_date(
        history_by_target=history_by_target,
        index_by_target_date=index_by_target_date,
    )
    if selected_equity_replay_keys is None:
        (
            selected_equity_replay_keys,
            precomputed_layer_outputs,
            precomputed_option_expression_plans,
            _,
        ) = _select_candidate_policy_portfolio_replay_keys(
            bars_by_target=bars_by_target,
            candidate_model_ref=candidate_model_ref,
            after_cost_alpha_model=after_cost_alpha_model,
            entry_calibration=entry_calibration,
            option_candidates_by_underlying_time=option_candidates_by_underlying_time,
            initial_capital_usd=DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
            max_positions=DEFAULT_PORTFOLIO_MAX_POSITIONS,
            default_target_allocation_fraction=DEFAULT_TARGET_ALLOCATION_FRACTION,
            switch_minimum_rank_score_delta=0.05,
        )
    precomputed_layer_outputs = precomputed_layer_outputs or {}
    precomputed_option_expression_plans = precomputed_option_expression_plans or {}
    replay_items: list[tuple[float, str, int]] = []
    for target in sorted(history_by_target):
        for index, bar in enumerate(history_by_target[target][:-1]):
            key = (target, index)
            if str(bar.get("asset_class") or "") == "us_equity" and key not in selected_equity_replay_keys:
                continue
            replay_items.append((_timestamp_sort_key(_replay_time_pointer_for_bar(bar)), target, index))
    for _, target, index in sorted(replay_items, key=lambda item: (item[0], item[1], item[2])):
            target_rows = history_by_target[target]
            bar = target_rows[index]
            if max_decision_rows is not None and len(rows) >= max_decision_rows:
                return rows
            next_bar = target_rows[index + 1]
            replay_time_pointer = _replay_time_pointer_for_bar(bar)
            date_text = str(bar["date"])
            market_universe = market_universe_by_date.get(date_text, ())
            reference_price = float(bar["bar_close"])
            layer_outputs = dict(precomputed_layer_outputs.get((target, index)) or {})
            if not layer_outputs:
                layer_outputs = _candidate_layer_outputs(
                    target=target,
                    target_rows=target_rows,
                    index=index,
                    market_universe=market_universe,
                    reference_price=reference_price,
                    candidate_model_ref=candidate_model_ref,
                    after_cost_alpha_model=after_cost_alpha_model,
                    entry_calibration=entry_calibration.artifact,
                )
            option_candidates: Sequence[Mapping[str, Any]] = ()
            key = (target, index)
            option_expression_plan: Mapping[str, Any] | None = precomputed_option_expression_plans.get(key)
            if str(bar.get("asset_class") or "") == "us_equity" and _option_expression_signal_required(layer_outputs):
                option_candidates = option_candidates_by_underlying_time.get((target.upper(), replay_time_pointer), ())
                if option_expression_plan is None and not option_candidates:
                    if allow_option_feature_requirements:
                        missing_option_feature_requirements.append(
                            _replay_option_feature_requirement_sample(target=target, timestamp=replay_time_pointer)
                        )
                        continue
                elif option_expression_plan is None:
                    option_expression_plan = _option_expression_plan_for_bar(
                        bar=bar,
                        candidate_model_ref=candidate_model_ref,
                        timestamp=replay_time_pointer,
                        layer_outputs=layer_outputs,
                        option_candidates=option_candidates,
                    )
            else:
                option_expression_plan = _option_expression_plan_for_bar(
                    bar=bar,
                    candidate_model_ref=candidate_model_ref,
                    timestamp=replay_time_pointer,
                    layer_outputs=layer_outputs,
                    option_candidates=option_candidates,
                )
            replay_market_snapshot = _replay_market_snapshot(
                bar=bar,
                target=target,
                date_text=date_text,
                option_expression_plan=option_expression_plan,
            )
            replay_trade_risk_cap = _trade_risk_cap(
                float(replay_market_snapshot["reference_price"]),
                option_expression_plan=option_expression_plan,
                allocation_context=_target_allocation_context(
                    layer_outputs=layer_outputs,
                    total_portfolio_notional_usd=total_portfolio_notional_usd,
                    default_target_allocation_fraction=default_target_allocation_fraction,
                ),
            )
            replay_result = build_replay_runtime_dry_run(
                account_sleeve_id=_account_sleeve_for_bar(bar),
                target_ref=target,
                market_universe=market_universe,
                target_context_rows=_target_market_universe_rows(market_universe=market_universe, target=target),
                target_context_state=layer_outputs["target_context_state"],
                event_state_vector=layer_outputs["event_state_vector"],
                unified_decision_vector=layer_outputs["unified_decision_vector"],
                option_expression_plan=option_expression_plan,
                residual_event_governance=_residual_event_governance_for_bar(
                    candidate_model_ref=candidate_model_ref,
                    timestamp=replay_time_pointer,
                    layer_outputs=layer_outputs,
                    option_expression_plan=option_expression_plan,
                ),
                trade_risk_cap=replay_trade_risk_cap,
                market_snapshot=replay_market_snapshot,
                replay_fill_policy={
                    "replay_fill_policy_ref": f"replay_fill_policy://{bar.get('asset_class', 'market')}_daily_close/slippage_10_fee_5_bps",
                    "slippage_bps": 10,
                    "fee_bps": 5,
                },
                generated_at_utc=str(bar["timestamp"]),
            )
            entry = replay_result["decision_records"]["entry_decision"]
            order_intent = replay_result["decision_records"]["execution_order_intent"]
            fill = replay_result["decision_records"]["simulated_fill_event"]
            fill_status = str(fill.get("fill_status") or "")
            selected_contract = _as_mapping(_as_mapping(option_expression_plan).get("selected_contract"))
            selected_option_contract_ref = str(selected_contract.get("contract_ref") or selected_contract.get("option_symbol") or "")
            asset_class = "us_option" if selected_option_contract_ref else entry.get("asset_class") or bar.get("asset_class")
            option_path_result = _option_contract_path_return(
                selected_option_contract_ref=selected_option_contract_ref,
                entry_timestamp=replay_time_pointer,
                exit_timestamp=str(next_bar["timestamp"]),
                option_contract_paths_by_symbol=option_contract_paths_by_symbol,
            )
            gross_return = (float(next_bar["bar_close"]) - reference_price) / reference_price
            return_source = "underlying_next_bar"
            option_contract_path_status = "not_applicable"
            option_contract_path_rejection_reason = None
            option_entry_price = option_exit_price = None
            if selected_option_contract_ref:
                if option_path_result:
                    gross_return = float(option_path_result["gross_return"])
                    return_source = "m05_option_expression_contract_path"
                    option_contract_path_status = "available"
                    option_entry_price = option_path_result["entry_price"]
                    option_exit_price = option_path_result["exit_price"]
                else:
                    gross_return = 0.0
                    return_source = "option_contract_path_missing"
                    option_contract_path_status = "missing"
                    option_contract_path_rejection_reason = "option_contract_path_missing"
                    if fill_status == "simulated_filled":
                        fill_status = "simulated_rejected"
            filled = fill_status == "simulated_filled"
            cost = REPLAY_COST_PER_FILLED_DECISION if filled else 0.0
            realized_return = gross_return if filled else 0.0
            outcome_label = None if option_contract_path_rejection_reason else (1 if gross_return > 0 else 0)
            decision_expression_type = _decision_expression_type(
                asset_class=str(asset_class or ""),
                option_expression_plan=option_expression_plan,
            )
            decision_instrument_scope = _decision_instrument_scope(
                asset_class=str(asset_class or ""),
                selected_option_contract_ref=selected_option_contract_ref,
            )
            path_context = _path_conditioning_context(
                target=target,
                decision_instrument_scope=decision_instrument_scope,
                selected_option_contract_ref=selected_option_contract_ref,
                option_expression_plan=option_expression_plan,
            )
            rows.append(
                {
                    "contract_type": REPLAY_DECISION_ROW_CONTRACT,
                    "replay_execution_run_id": run_id,
                    "decision_id": entry["entry_decision_id"],
                    "source_order_intent_id": order_intent["execution_order_intent_id"],
                    "source_fill_event_id": fill["simulated_fill_event_id"],
                    "candidate_model_ref": candidate_model_ref,
                    "replay_contract_ref": replay_contract_ref,
                    "account_sleeve_id": _account_sleeve_for_bar(bar),
                    "target_ref": target,
                    "instrument_ref": entry["instrument_ref"],
                    "asset_class": asset_class,
                    "decision_expression_type": decision_expression_type,
                    "decision_instrument_scope": decision_instrument_scope,
                    "path_conditioning_policy": path_context["path_conditioning_policy"],
                    "path_scope": path_context["path_scope"],
                    "candidate_set_scope": path_context["candidate_set_scope"],
                    "miss_attribution_layer": path_context["miss_attribution_layer"],
                    "asset_expression_route": str(_as_mapping(option_expression_plan).get("asset_expression_route") or ""),
                    "option_surface_status": str(_as_mapping(option_expression_plan).get("option_surface_status") or ""),
                    "selected_option_expression_type": _as_mapping(option_expression_plan).get("selected_expression_type"),
                    "selected_option_contract_ref": selected_option_contract_ref or None,
                    "selected_option_mid_price": selected_contract.get("mid_price"),
                    "option_contract_path_status": option_contract_path_status,
                    "replay_rejection_reason": option_contract_path_rejection_reason,
                    "option_entry_price": option_entry_price,
                    "option_exit_price": option_exit_price,
                    "return_source": return_source,
                    "timestamp": bar["timestamp"],
                    "replay_time_pointer": replay_time_pointer,
                    "point_in_time_policy": REPLAY_TIME_POINTER_POLICY_REF,
                    "next_timestamp": next_bar["timestamp"],
                    "decision_status": entry["decision_status"],
                    "decision_action": entry["decision_action"],
                    "action": entry["decision_action"],
                    "fill_status": fill_status,
                    "planned_order_quantity": order_intent.get("sizing_plan", {}).get("quantity"),
                    "planned_position_notional_usd": replay_trade_risk_cap.get("planned_position_notional_usd"),
                    "planned_unit_cost_usd": replay_trade_risk_cap.get("estimated_contract_cost_usd")
                    or replay_trade_risk_cap.get("planned_unit_cost_usd"),
                    "target_allocation_fraction": replay_trade_risk_cap.get("target_allocation_fraction"),
                    "target_allocation_fraction_source": replay_trade_risk_cap.get("target_allocation_fraction_source"),
                    "total_portfolio_notional_usd": replay_trade_risk_cap.get("total_portfolio_notional_usd"),
                    "position_sizing_policy": replay_trade_risk_cap.get("position_sizing_policy"),
                    "prediction_score": layer_outputs["prediction_score"],
                    "outcome_label": outcome_label,
                    "realized_return": realized_return,
                    "baseline_return": 0.0,
                    "cost": cost,
                    "bar_close": reference_price,
                    "next_bar_close": float(next_bar["bar_close"]),
                    "feature_daily_return": _daily_return(target_rows, index),
                    "feature_momentum_7d": _window_return(target_rows, index, 7),
                    "feature_momentum_30d": _window_return(target_rows, index, 30),
                    "feature_volume_rank_30d": _volume_rank(target_rows, index, 30),
                    "entry_threshold_calibration_ref": str(entry_calibration.path),
                    "entry_threshold_calibration_status": entry_calibration.artifact["calibration_status"],
                    "entry_threshold_calibration_role": _entry_calibration_role(
                        timestamp=str(bar["timestamp"]),
                        entry_calibration=entry_calibration.artifact,
                    ),
                    "entry_minimum_alpha_confidence": entry_calibration.minimum_entry_alpha_confidence,
                    "entry_minimum_trade_intensity": entry_calibration.minimum_trade_intensity,
                    "model_evidence_chain": list(MODEL_EVIDENCE_CHAIN),
                    "model_evidence_mode": "component_input_model_evidence_generators",
                    "model_layer_refs": layer_outputs["model_layer_refs"],
                    "model_layer_diagnostics": layer_outputs["model_layer_diagnostics"],
                    "validation_status": replay_result["validation_status"],
                    "side_effects": replay_result["side_effects"],
                }
            )
    if missing_option_feature_requirements:
        artifact_ref = _write_replay_option_feature_requirements(
            path=option_feature_requirements_path,
            requirements=missing_option_feature_requirements,
        )
        raise _replay_option_feature_acquisition_error(
            missing_option_feature_requirements,
            artifact_ref=artifact_ref,
        )
    return rows


def _decision_expression_type(*, asset_class: str, option_expression_plan: Mapping[str, Any] | None) -> str:
    if asset_class == "us_option":
        selected_expression_type = str(_as_mapping(option_expression_plan).get("selected_expression_type") or "").strip()
        return selected_expression_type or "listed_option"
    if asset_class == "crypto_spot":
        return "crypto_spot"
    if asset_class == "us_equity":
        return "underlying_equity"
    return asset_class or "unknown"


def _decision_instrument_scope(*, asset_class: str, selected_option_contract_ref: str) -> str:
    if asset_class == "us_option" or selected_option_contract_ref:
        return "listed_option_contract"
    if asset_class == "crypto_spot":
        return "crypto_spot"
    if asset_class == "us_equity":
        return "underlying_equity"
    return asset_class or "unknown"


def _path_conditioning_context(
    *,
    target: str,
    decision_instrument_scope: str,
    selected_option_contract_ref: str,
    option_expression_plan: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Describe the replay branch whose non-taken opportunities are reviewable."""

    selected_target = str(target or "").upper() or "unknown"
    option_plan = _as_mapping(option_expression_plan)
    if selected_option_contract_ref:
        candidate_set_scope = "selected_target_selected_option_contract_path"
        miss_layer = "model_05_option_expression"
    elif option_plan:
        candidate_set_scope = "selected_target_option_expression_candidates"
        miss_layer = "model_05_option_expression"
    elif decision_instrument_scope == "underlying_equity":
        candidate_set_scope = "selected_target_underlying_decision"
        miss_layer = "model_04_unified_decision"
    else:
        candidate_set_scope = f"selected_target_{decision_instrument_scope or 'unknown'}"
        miss_layer = "current_decision_layer"
    return {
        "path_conditioning_policy": "upstream_selected_path_only",
        "path_scope": f"selected_target:{selected_target}",
        "candidate_set_scope": candidate_set_scope,
        "miss_attribution_layer": miss_layer,
    }


def _market_universe_for_date(
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    index_by_target_date: Mapping[str, Mapping[str, int]],
    date_text: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in sorted(bars_by_target):
        index = index_by_target_date[target].get(date_text)
        if index is None:
            continue
        bar = bars_by_target[target][index]
        rows.append(
            {
                "target_ref": target,
                "instrument_ref": bar["symbol"],
                "asset_class": str(bar.get("asset_class") or "crypto_spot"),
                "reference_price": bar["bar_close"],
            }
        )
    return rows


def _target_market_universe_rows(
    *,
    market_universe: Sequence[Mapping[str, Any]],
    target: str,
) -> tuple[Mapping[str, Any], ...]:
    normalized = str(target).upper()
    rows = tuple(row for row in market_universe if str(row.get("target_ref") or row.get("symbol") or "").upper() == normalized)
    return rows or tuple(market_universe)


def _market_universe_by_date(
    *,
    history_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    index_by_target_date: Mapping[str, Mapping[str, int]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    market_dates = sorted({str(row["date"]) for rows in history_by_target.values() for row in rows})
    return {
        date_text: tuple(_market_universe_for_date(history_by_target, index_by_target_date, date_text))
        for date_text in market_dates
    }


def _load_candidate_policy_bars(
    *,
    plan_path: Path,
    include_crypto: bool,
    include_equity: bool,
    equity_source_root: Path,
    equity_symbols: Sequence[str] | None = None,
    replay_month: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_target = _load_crypto_bars(plan_path, replay_month=replay_month) if include_crypto else {}
    if include_equity:
        equity_rows = _load_equity_bars_from_plan(
            plan_path=plan_path,
            replay_month=replay_month,
            equity_symbols=equity_symbols,
        )
        if equity_rows and equity_symbols:
            missing_symbols = sorted(_string_set(equity_symbols) - set(equity_rows))
            if missing_symbols:
                equity_rows.update(
                    _load_equity_bars(
                        equity_source_root=equity_source_root,
                        equity_symbols=missing_symbols,
                    )
                )
        if not equity_rows:
            equity_rows = _load_equity_bars(equity_source_root=equity_source_root, equity_symbols=equity_symbols)
        for target, rows in equity_rows.items():
            if rows:
                rows_by_target[target] = rows
    return rows_by_target


def _candidate_handoff_for_replay(
    *,
    database_url: str | None,
    schema: str,
    table: str,
    candidate_universe_path: Path,
    explicit_equity_symbols: Sequence[str] | None,
    include_equity: bool,
    replay_month: str | None,
) -> dict[str, Any]:
    explicit_symbols = tuple(sorted(_string_set(explicit_equity_symbols)))
    if not include_equity:
        return {
            "status": "not_applicable",
            "source": "equity_replay_disabled",
            "candidate_symbols": (),
            "row_count": 0,
        }
    if explicit_symbols:
        return {
            "status": "override",
            "source": "explicit_candidate_symbols_override",
            "candidate_symbols": explicit_symbols,
            "row_count": len(explicit_symbols),
        }
    target_candidate_rows = _load_target_candidate_handoff_rows(candidate_universe_path)
    if target_candidate_rows:
        symbols = tuple(
            sorted(
                {
                    str(row.get("routing_symbol_ref") or row.get("audit_symbol_ref") or row.get("target_symbol") or "").upper()
                    for row in target_candidate_rows
                    if str(row.get("routing_symbol_ref") or row.get("audit_symbol_ref") or row.get("target_symbol") or "").strip()
                }
            )
        )
        if symbols:
            return {
                "status": "available",
                "source": "layer_02_target_candidate_handoff",
                "candidate_symbols": symbols,
                "row_count": len(target_candidate_rows),
                "artifact_ref": str(candidate_universe_path),
            }
    fixed_rows = _load_fixed_historical_candidate_universe_rows(candidate_universe_path)
    if fixed_rows:
        symbols = tuple(
            sorted(
                {
                    str(row.get("symbol") or row.get("target_ref") or "").upper()
                    for row in fixed_rows
                    if str(row.get("asset_class") or "").strip().lower() == "us_equity"
                    and str(row.get("symbol") or row.get("target_ref") or "").strip()
                }
            )
        )
        if not symbols:
            raise ValueError(
                "fixed historical candidate universe contains no active us_equity candidates: "
                f"{candidate_universe_path}"
            )
        return {
            "status": "available",
            "source": "fixed_current_snapshot_historical_candidate_universe",
            "candidate_symbols": symbols,
            "row_count": len(fixed_rows),
            "artifact_ref": str(candidate_universe_path),
        }
    rows = _load_layer_two_candidate_handoff_rows(
        database_url=database_url,
        schema=schema,
        table=table,
        replay_month=replay_month,
    )
    symbols = tuple(sorted({str(row.get("holding_symbol") or "").upper() for row in rows if row.get("holding_symbol")}))
    if not symbols:
        raise ValueError(
            "equity/options replay requires Layer 2 target-candidate handoff rows from "
            f"{schema}.{table}; base_context pre_replay_target_refs are Layer 1/2 context only and are not trade candidates"
        )
    return {
        "status": "available",
        "source": "layer_02_target_candidate_handoff",
        "candidate_symbols": symbols,
        "row_count": len(rows),
    }


def _load_target_candidate_handoff_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".jsonl" or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                continue
            status = str(payload.get("candidate_eligibility_state") or "eligible").strip().lower()
            if status not in {"eligible", "active", "accepted"}:
                continue
            rows.append(dict(payload))
    return rows


def _resolved_candidate_universe_path(*, dataset_root: Path, candidate_universe_path: Path | None) -> Path:
    if candidate_universe_path is not None:
        return candidate_universe_path
    try:
        storage_repo_root = dataset_root.parents[2]
    except IndexError:
        return Path(DEFAULT_CANDIDATE_UNIVERSE_FILENAME)
    return storage_repo_root / "main" / "shared" / DEFAULT_CANDIDATE_UNIVERSE_FILENAME


def _load_fixed_historical_candidate_universe_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            row = {str(key): str(value or "").strip() for key, value in raw.items()}
            symbol = str(row.get("symbol") or row.get("target_ref") or "").upper()
            status = str(row.get("replay_candidate_status") or row.get("pool_membership_status") or "active").lower()
            if not symbol or status != "active":
                continue
            rows.append(row)
    return rows


def _validate_equity_candidate_bar_coverage(
    *,
    include_equity: bool,
    explicit_equity_symbols: Sequence[str] | None,
    candidate_handoff: Mapping[str, Any],
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    if not include_equity:
        return
    expected = set(_string_set(candidate_handoff.get("candidate_symbols")))
    if not expected:
        return
    loaded = {
        target
        for target, rows in bars_by_target.items()
        if rows and str(rows[0].get("asset_class") or "") == "us_equity"
    }
    if loaded:
        missing = sorted(expected - loaded)
        if not missing:
            return
    source = str(candidate_handoff.get("source") or "")
    if source == "explicit_candidate_symbols_override" and explicit_equity_symbols:
        return
    missing = sorted(expected - loaded)
    if missing:
        sample = ", ".join(missing[:20])
        raise ValueError(
            "Layer 2 target-candidate handoff produced equity/options candidates but replay is missing "
            f"materialized candidate bars for {len(missing)} of {len(expected)} symbols; sample={sample}. "
            "Run the monthly on-demand Alpaca candidate acquisition for the fixed historical candidate universe before replay execution"
        )
    raise ValueError(
        "Layer 2 target-candidate handoff produced equity/options candidates but replay found no materialized "
        "candidate bars; run the monthly on-demand Alpaca candidate acquisition before replay execution"
    )


def _prune_fixed_candidate_handoff_no_history_symbols(
    *,
    candidate_handoff: Mapping[str, Any],
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    equity_source_root: Path,
    replay_month: str | None,
) -> dict[str, Any]:
    pruned = dict(candidate_handoff)
    if str(candidate_handoff.get("source") or "") != "fixed_current_snapshot_historical_candidate_universe":
        return pruned
    expected = set(_string_set(candidate_handoff.get("candidate_symbols")))
    loaded = set(bars_by_target)
    missing = sorted(expected - loaded)
    if not missing:
        pruned["excluded_no_historical_bar_symbols"] = ()
        return pruned
    no_history = _completed_empty_equity_source_symbols(
        equity_source_root=equity_source_root,
        symbols=missing,
        replay_month=replay_month,
    )
    if not no_history:
        pruned["excluded_no_historical_bar_symbols"] = ()
        return pruned
    pruned["candidate_symbols"] = tuple(sorted(expected - set(no_history)))
    pruned["excluded_no_historical_bar_symbols"] = tuple(no_history)
    return pruned


def _completed_empty_equity_source_symbols(
    *,
    equity_source_root: Path,
    symbols: Sequence[str],
    replay_month: str | None,
) -> tuple[str, ...]:
    no_history: list[str] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol).upper()
        symbol_dir = equity_source_root / symbol
        if not symbol_dir.exists():
            continue
        if replay_month:
            month_dirs = [symbol_dir / replay_month]
        else:
            month_dirs = [
                symbol_dir / f"{year:04d}-{month:02d}"
                for year in range(2021, 2026)
                for month in range(1, 13)
            ]
        if month_dirs and all(_completion_receipt_succeeded(month_dir / "completion_receipt.json") for month_dir in month_dirs):
            no_history.append(symbol)
    return tuple(sorted(no_history))


def _load_layer_two_candidate_handoff_rows(
    *,
    database_url: str | None,
    schema: str,
    table: str,
    replay_month: str | None,
) -> list[dict[str, Any]]:
    if not database_url:
        return []
    _validate_identifier(schema)
    _validate_identifier(table)
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load Layer 2 replay candidate handoff rows") from exc
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return []
            cursor.execute(
                f"""
                SELECT
                  h."etf_symbol",
                  h."as_of_date",
                  h."available_time",
                  h."holding_symbol",
                  h."holding_name",
                  h."weight",
                  h."sector_type"
                FROM "{schema}"."{table}" AS h
                WHERE h."holding_symbol" IS NOT NULL
                ORDER BY h."available_time" ASC, h."etf_symbol" ASC, h."holding_symbol" ASC
                """
            )
            rows = [dict(row) for row in cursor.fetchall()]
    if replay_month:
        return [row for row in rows if _candidate_handoff_row_visible_in_month(row, replay_month)]
    return rows


def _candidate_handoff_row_visible_in_month(row: Mapping[str, Any], replay_month: str) -> bool:
    if len(replay_month) != 7 or replay_month[4] != "-":
        return True
    available_time = str(row.get("available_time") or row.get("as_of_date") or "")
    as_of_date = str(row.get("as_of_date") or "")
    return available_time[:7] <= replay_month and (not as_of_date or as_of_date[:7] <= replay_month)


def _candidate_handoff_allows_option_feature_requirements(candidate_handoff: Mapping[str, Any]) -> bool:
    return str(candidate_handoff.get("source") or "") in {
        "fixed_current_snapshot_historical_candidate_universe",
        "layer_02_target_candidate_handoff",
    }


def _option_feature_requirement_policy(candidate_handoff: Mapping[str, Any]) -> str:
    if str(candidate_handoff.get("source") or "") == "fixed_current_snapshot_historical_candidate_universe":
        return "fixed_historical_candidate_universe_allows_replay_option_feature_requirements"
    if str(candidate_handoff.get("source") or "") == "layer_02_target_candidate_handoff":
        return "point_in_time_candidate_handoff_allows_on_demand_option_feature_requirements"
    return "static_candidate_universe_does_not_authorize_provider_acquisition"


def _manifest_equity_target_refs(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    refs = _string_set(manifest.get("pre_replay_target_refs"))
    return tuple(sorted(ref for ref in refs if ref not in CRYPTO_SYMBOLS_BY_INSTRUMENT.values()))


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return {stripped.upper()} if stripped else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().upper() for item in value if str(item).strip()}
    return set()


class _LazyOptionCandidateFeatures:
    """Point-in-time option candidates loaded only after replay emits a signal."""

    def __init__(self, *, database_url: str | None, schema: str, table: str) -> None:
        self.database_url = database_url
        self.schema = schema
        self.table = table
        self._cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def get(self, key: tuple[str, str], default: Sequence[Mapping[str, Any]] = ()) -> Sequence[Mapping[str, Any]]:
        target, timestamp = key
        normalized_key = (str(target).upper(), _time_key(timestamp))
        if normalized_key not in self._cache:
            self._cache[normalized_key] = _load_option_candidate_features_for_timestamp(
                database_url=self.database_url,
                schema=self.schema,
                table=self.table,
                target=normalized_key[0],
                timestamp=normalized_key[1],
            )
        return self._cache[normalized_key] or default

    def values(self) -> Sequence[Sequence[Mapping[str, Any]]]:
        return tuple(self._cache.values())

    def __len__(self) -> int:
        return sum(1 for rows in self._cache.values() if rows)


def _option_candidate_feature_row_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    underlying = str(row.get("underlying") or "").upper()
    snapshot_time = _time_key(row.get("snapshot_time"))
    snapshot_type = str(row.get("snapshot_type") or "")
    contract_ref = str(row.get("option_symbol") or "")
    payload = _coerce_json_mapping(row.get("feature_payload_json"))
    diagnostics = _coerce_json_mapping(row.get("feature_quality_diagnostics"))
    if snapshot_type == OPTION_SOURCE_UNAVAILABLE_SNAPSHOT_TYPE or payload.get("option_surface_status") == OPTION_SOURCE_UNAVAILABLE_STATUS:
        if not underlying or not snapshot_time:
            return None
        return {
            "contract_ref": OPTION_SOURCE_UNAVAILABLE_SYMBOL,
            "option_symbol": OPTION_SOURCE_UNAVAILABLE_SYMBOL,
            "underlying": underlying,
            "snapshot_time": snapshot_time,
            "snapshot_type": OPTION_SOURCE_UNAVAILABLE_SNAPSHOT_TYPE,
            "option_surface_status": OPTION_SOURCE_UNAVAILABLE_STATUS,
            "asset_expression_route": "option_expression_unfilled",
            "candidate_quality_diagnostics": diagnostics,
            **payload,
        }
    if not underlying or not snapshot_time or not contract_ref:
        return None
    option_right = payload.get("option_right") or payload.get("right") or payload.get("option_right_type")
    expiration = payload.get("expiration") or row.get("expiration")
    dte = payload.get("dte") or payload.get("days_to_expiration")
    mid = payload.get("mid_price") or payload.get("mid")
    implied_vol = payload.get("iv") or payload.get("implied_volatility") or payload.get("implied_vol")
    return {
        "contract_ref": contract_ref,
        "option_symbol": contract_ref,
        "option_right": option_right,
        "right": option_right,
        "expiration": expiration,
        "dte": dte,
        "days_to_expiration": dte,
        "mid_price": mid,
        "mid": mid,
        "iv": implied_vol,
        "implied_volatility": implied_vol,
        "candidate_quality_diagnostics": diagnostics,
        **payload,
    }


def _load_option_candidate_features_for_timestamp(
    *,
    database_url: str | None,
    schema: str,
    table: str,
    target: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    if not database_url or not target or not timestamp:
        return []
    _validate_identifier(schema)
    _validate_identifier(table)
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load replay option feature rows") from exc
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return []
            cursor.execute(
                f"""
                SELECT
                  f."underlying",
                  f."snapshot_time",
                  f."snapshot_type",
                  f."option_symbol",
                  f."feature_payload_json",
                  f."feature_quality_diagnostics"
                FROM "{schema}"."{table}" AS f
                WHERE f."underlying" = %s
                  AND f."snapshot_time" = %s::timestamptz
                  AND COALESCE(f."snapshot_type", 'entry') IN ('entry', 'source_cache', 'source_unavailable')
                ORDER BY f."option_symbol" ASC
                """,
                (target, timestamp),
            )
            feature_rows = [dict(row) for row in cursor.fetchall()]
    output: list[dict[str, Any]] = []
    for row in feature_rows:
        payload = _option_candidate_feature_row_payload(row)
        if payload is not None:
            output.append(payload)
    return output


def _load_option_candidate_features(
    *,
    database_url: str | None,
    schema: str,
    table: str,
    targets: Iterable[str],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not database_url:
        return {}
    _validate_identifier(schema)
    _validate_identifier(table)
    target_filter = sorted({str(target).upper() for target in targets if target})
    if not target_filter:
        return {}
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load replay option feature rows") from exc
    rows_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return {}
            cursor.execute(
                f"""
                SELECT
                  f."underlying",
                  f."snapshot_time",
                  f."snapshot_type",
                  f."option_symbol",
                  f."feature_payload_json",
                  f."feature_quality_diagnostics"
                FROM "{schema}"."{table}" AS f
                WHERE f."underlying" = ANY(%s)
                  AND COALESCE(f."snapshot_type", 'entry') IN ('entry', 'source_cache', 'source_unavailable')
                ORDER BY f."underlying" ASC, f."snapshot_time" ASC, f."option_symbol" ASC
                """,
                (target_filter,),
            )
            feature_rows = [dict(row) for row in cursor.fetchall()]
    for row in feature_rows:
        underlying = str(row.get("underlying") or "").upper()
        snapshot_time = _time_key(row.get("snapshot_time"))
        payload = _option_candidate_feature_row_payload(row)
        if not underlying or not snapshot_time or payload is None:
            continue
        rows_by_key[(underlying, snapshot_time)].append(payload)
    return rows_by_key


def _load_option_contract_path_bars(
    *,
    database_url: str | None,
    schema: str,
    table: str,
    targets: Iterable[str],
) -> dict[str, list[dict[str, Any]]]:
    if not database_url:
        return {}
    _validate_identifier(schema)
    _validate_identifier(table)
    target_filter = sorted({str(target).upper() for target in targets if target})
    if not target_filter:
        return {}
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load replay option contract path rows") from exc
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return {}
            cursor.execute(
                f"""
                SELECT
                  p."underlying",
                  p."option_symbol",
                  p."timestamp",
                  p."bar_close"
                FROM "{schema}"."{table}" AS p
                WHERE p."underlying" = ANY(%s)
                  AND p."bar_close" IS NOT NULL
                ORDER BY p."option_symbol" ASC, p."timestamp" ASC
                """,
                (target_filter,),
            )
            path_rows = [dict(row) for row in cursor.fetchall()]
    for row in path_rows:
        option_symbol = str(row.get("option_symbol") or "").upper()
        timestamp_key = _time_key(row.get("timestamp"))
        close = _safe_float(row.get("bar_close"))
        if not option_symbol or not timestamp_key or close is None or close <= 0:
            continue
        rows_by_symbol[option_symbol].append(
            {
                "option_symbol": option_symbol,
                "timestamp": timestamp_key,
                "bar_close": close,
            }
        )
    return rows_by_symbol


def _default_option_feature_database_url() -> str | None:
    for env_name in ("OPENCLAW_DATABASE_URL", "DATABASE_URL"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    if DEFAULT_DB_URL_FILE.exists():
        return DEFAULT_DB_URL_FILE.read_text(encoding="utf-8").strip()
    return None


def _load_crypto_bars(plan_path: Path, *, replay_month: str | None = None) -> dict[str, list[dict[str, Any]]]:
    rows_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with plan_path.open(newline="", encoding="utf-8") as handle:
        for plan_row in csv.DictReader(handle):
            if plan_row.get("source_id") != "okx_crypto_market_data" or plan_row.get("coverage_status") != "available":
                continue
            if replay_month and plan_row.get("month") != replay_month:
                continue
            receipt = _load_json(Path(str(plan_row["coverage_receipt_path"])))
            for output in _latest_succeeded_outputs(receipt):
                path = Path(str(output))
                if path.name != "crypto_bar.csv":
                    continue
                for bar in _read_bar_csv(path):
                    target = CRYPTO_SYMBOLS_BY_INSTRUMENT.get(str(bar["symbol"]).upper())
                    if target:
                        bar["symbol"] = str(bar["symbol"]).upper()
                        bar["asset_class"] = "crypto_spot"
                        bar["source_id"] = "okx_crypto_market_data"
                        rows_by_target[target].append(bar)
    deduped: dict[str, list[dict[str, Any]]] = {}
    for target, rows in rows_by_target.items():
        by_timestamp = {str(row["timestamp"]): row for row in rows}
        deduped[target] = sorted(by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    return deduped


def _load_equity_bars_from_plan(
    *,
    plan_path: Path,
    replay_month: str | None,
    equity_symbols: Sequence[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    symbol_filter = {str(symbol).upper() for symbol in equity_symbols or []}
    with plan_path.open(newline="", encoding="utf-8") as handle:
        for plan_row in csv.DictReader(handle):
            if plan_row.get("source_id") != "alpaca_bars" or plan_row.get("coverage_status") != "available":
                continue
            if replay_month and plan_row.get("month") != replay_month:
                continue
            symbol = str(plan_row.get("target_ref") or "").upper()
            if not symbol or (symbol_filter and symbol not in symbol_filter):
                continue
            receipt = _load_json(Path(str(plan_row["coverage_receipt_path"])))
            csv_rows_loaded = False
            for output in _latest_succeeded_outputs(receipt):
                path = Path(str(output))
                if path.name != "equity_bar.csv":
                    continue
                for row in _read_bar_csv(path):
                    if replay_month and str(row["timestamp"])[:7] != replay_month:
                        continue
                    row["timestamp"] = _equity_market_close_timestamp(
                        str(row.get("date") or _sql_bar_date(row["timestamp"]))
                    )
                    row["symbol"] = symbol
                    row["asset_class"] = "us_equity"
                    row["source_id"] = "alpaca_bars"
                    rows_by_target[symbol].append(row)
                    csv_rows_loaded = True
            if not csv_rows_loaded:
                rows_by_target[symbol].extend(
                    _load_equity_bars_from_sql(
                        symbol=symbol,
                        start_date=str(plan_row.get("start_date") or ""),
                        end_date_exclusive=str(plan_row.get("end_date_exclusive") or ""),
                        database_url=_default_option_feature_database_url(),
                    )
                )
    deduped: dict[str, list[dict[str, Any]]] = {}
    for target, rows in rows_by_target.items():
        by_timestamp = {str(row["timestamp"]): row for row in rows}
        deduped[target] = sorted(by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    return deduped


def _load_equity_bars(*, equity_source_root: Path, equity_symbols: Sequence[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    rows_by_target: dict[str, list[dict[str, Any]]] = {}
    if not equity_source_root.exists():
        return rows_by_target
    symbol_filter = {str(symbol).upper() for symbol in equity_symbols or []}
    daily_by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    sql_windows_by_symbol: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for symbol_dir in sorted(path for path in equity_source_root.iterdir() if path.is_dir()):
        symbol = symbol_dir.name.upper()
        if symbol_filter and symbol not in symbol_filter:
            continue
        daily: dict[str, dict[str, Any]] = {}
        daily_by_symbol[symbol] = daily
        for month_dir in sorted(path for path in symbol_dir.iterdir() if path.is_dir()):
            if month_dir.name < "2021-01" or month_dir.name > "2025-12":
                continue
            csv_rows_loaded = False
            for csv_path in sorted(month_dir.glob("runs/*/saved/equity_bar.csv")):
                for row in _read_bar_csv(csv_path):
                    timestamp = str(row["timestamp"])
                    year_month = timestamp[:7]
                    if year_month < "2021-01" or year_month > "2025-12":
                        continue
                    date_text = str(row["date"])
                    _merge_daily_equity_bar(daily=daily, symbol=symbol, row=row, date_text=date_text)
                    csv_rows_loaded = True
            if csv_rows_loaded or not _completion_receipt_succeeded(month_dir / "completion_receipt.json"):
                continue
            window = _month_window(month_dir.name)
            if window is None:
                continue
            sql_windows_by_symbol[symbol].append(window)
    sql_rows_by_symbol = _load_equity_bars_from_sql_bulk(
        symbol_windows=sql_windows_by_symbol,
        database_url=_default_option_feature_database_url(),
    )
    for symbol, sql_rows in sql_rows_by_symbol.items():
        daily = daily_by_symbol.setdefault(symbol, {})
        for row in sql_rows:
            _merge_daily_equity_bar(daily=daily, symbol=symbol, row=row, date_text=str(row["date"]))
    for symbol, daily in daily_by_symbol.items():
        rows = sorted(daily.values(), key=lambda row: str(row["timestamp"]))
        if len(rows) >= 2:
            rows_by_target[symbol] = rows
    return rows_by_target


def _merge_daily_equity_bar(
    *,
    daily: dict[str, dict[str, Any]],
    symbol: str,
    row: Mapping[str, Any],
    date_text: str,
) -> None:
    current = daily.get(date_text)
    if current is None:
        daily[date_text] = {
            "symbol": symbol,
            "asset_class": "us_equity",
            "source_id": "alpaca_bars",
            "timeframe": "1Day",
            "timestamp": _equity_market_close_timestamp(date_text),
            "date": date_text,
            "bar_open": float(row["bar_open"]),
            "bar_high": float(row["bar_high"]),
            "bar_low": float(row["bar_low"]),
            "bar_close": float(row["bar_close"]),
            "bar_volume": float(row["bar_volume"]),
        }
        return
    current["bar_high"] = max(float(current["bar_high"]), float(row["bar_high"]))
    current["bar_low"] = min(float(current["bar_low"]), float(row["bar_low"]))
    current["bar_close"] = float(row["bar_close"])
    current["bar_volume"] = float(current["bar_volume"]) + float(row["bar_volume"])


def _completion_receipt_succeeded(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        receipt = _load_json(path)
    except (json.JSONDecodeError, OSError, ValueError):
        return False
    runs = receipt.get("runs")
    return isinstance(runs, list) and any(isinstance(run, Mapping) and run.get("status") == "succeeded" for run in runs)


def _month_window(month: str) -> tuple[str, str] | None:
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
    except ValueError:
        return None
    if month_number < 1 or month_number > 12:
        return None
    start = f"{year:04d}-{month_number:02d}-01"
    if month_number == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month_number + 1:02d}-01"
    return start, end


def _load_equity_bars_from_sql_bulk(
    *,
    symbol_windows: Mapping[str, Sequence[tuple[str, str]]],
    database_url: str | None,
    schema: str = "trading_data",
    table: str = "model_01_market_regime_data_acquisition",
) -> dict[str, list[dict[str, Any]]]:
    normalized_windows = {
        str(symbol).upper(): tuple((str(start), str(end)) for start, end in windows)
        for symbol, windows in symbol_windows.items()
        if str(symbol).strip() and windows
    }
    if not database_url or not normalized_windows:
        return {}
    _validate_identifier(schema)
    _validate_identifier(table)
    starts = [start for windows in normalized_windows.values() for start, _ in windows]
    ends = [end for windows in normalized_windows.values() for _, end in windows]
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load SQL-retained replay equity bars") from exc
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return {}
            cursor.execute(
                f"""
                SELECT
                  b."symbol",
                  b."timeframe",
                  b."timestamp",
                  b."bar_open",
                  b."bar_high",
                  b."bar_low",
                  b."bar_close",
                  b."bar_volume"
                FROM "{schema}"."{table}" AS b
                WHERE b."symbol" = ANY(%s)
                  AND b."timestamp" >= %s::timestamptz
                  AND b."timestamp" < %s::timestamptz
                  AND b."bar_close" IS NOT NULL
                ORDER BY b."symbol" ASC, b."timestamp" ASC
                """,
                (list(sorted(normalized_windows)), min(starts), max(ends)),
            )
            rows = [dict(row) for row in cursor.fetchall()]
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        windows = normalized_windows.get(symbol)
        if not windows:
            continue
        date_text = _sql_bar_date(row.get("timestamp"))
        if not date_text or not any(start <= date_text < end for start, end in windows):
            continue
        parsed = _sql_equity_bar_row(row=row, symbol=symbol)
        if parsed is not None:
            rows_by_symbol[symbol].append(parsed)
    return {symbol: rows for symbol, rows in rows_by_symbol.items()}


def _load_equity_bars_from_sql(
    *,
    symbol: str,
    start_date: str,
    end_date_exclusive: str,
    database_url: str | None,
    schema: str = "trading_data",
    table: str = "model_01_market_regime_data_acquisition",
) -> list[dict[str, Any]]:
    if not database_url or not symbol or not start_date or not end_date_exclusive:
        return []
    _validate_identifier(schema)
    _validate_identifier(table)
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required to load SQL-retained replay equity bars") from exc
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) AS table_ref", (f"{schema}.{table}",))
            exists = cursor.fetchone()
            if not exists or exists.get("table_ref") is None:
                return []
            cursor.execute(
                f"""
                SELECT
                  b."symbol",
                  b."timeframe",
                  b."timestamp",
                  b."bar_open",
                  b."bar_high",
                  b."bar_low",
                  b."bar_close",
                  b."bar_volume"
                FROM "{schema}"."{table}" AS b
                WHERE b."symbol" = %s
                  AND b."timestamp" >= %s::timestamptz
                  AND b."timestamp" < %s::timestamptz
                  AND b."bar_close" IS NOT NULL
                ORDER BY b."timestamp" ASC
                """,
                (symbol, start_date, end_date_exclusive),
            )
            rows = [dict(row) for row in cursor.fetchall()]
    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        parsed = _sql_equity_bar_row(row=row, symbol=symbol)
        if parsed is not None:
            parsed_rows.append(parsed)
    return parsed_rows


def _sql_equity_bar_row(*, row: Mapping[str, Any], symbol: str) -> dict[str, Any] | None:
    date_text = _sql_bar_date(row.get("timestamp"))
    if not date_text:
        return None
    return {
        "symbol": str(row.get("symbol") or symbol).upper(),
        "asset_class": "us_equity",
        "source_id": "alpaca_bars",
        "timeframe": str(row.get("timeframe") or "1Day"),
        "timestamp": _equity_market_close_timestamp(date_text),
        "date": date_text,
        "bar_open": float(row["bar_open"]),
        "bar_high": float(row["bar_high"]),
        "bar_low": float(row["bar_low"]),
        "bar_close": float(row["bar_close"]),
        "bar_volume": float(row.get("bar_volume") or 0.0),
    }


def _sql_bar_date(value: Any) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    text = str(value or "")
    return text.split("T", 1)[0].split(" ", 1)[0] if text else ""


def _equity_market_close_timestamp(date_text: str) -> str:
    parsed = datetime.fromisoformat(str(date_text)[:10])
    return datetime.combine(parsed.date(), time(16, 0), tzinfo=NEW_YORK).isoformat()


def _account_sleeve_for_bar(bar: Mapping[str, Any]) -> str:
    return CRYPTO_SPOT_ACCOUNT_SLEEVE if str(bar.get("asset_class") or "") == "crypto_spot" else EQUITY_OPTIONS_ACCOUNT_SLEEVE


def _option_expression_plan_for_bar(
    *,
    bar: Mapping[str, Any],
    candidate_model_ref: str,
    timestamp: str,
    layer_outputs: Mapping[str, Any],
    option_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if str(bar.get("asset_class") or "") == "crypto_spot":
        return None
    target = str(bar.get("symbol") or "").upper()
    if not _option_expression_signal_required(layer_outputs):
        return None
    if _option_source_unavailable(option_candidates):
        return {
            "model_ref": f"{candidate_model_ref}/model_05_option_expression/{target}_{_time_key(timestamp)}_option_source_unavailable",
            "target_ref": target,
            "asset_expression_route": "option_expression_unfilled",
            "option_surface_status": OPTION_SOURCE_UNAVAILABLE_STATUS,
            "selected_expression_type": "no_option_source_available",
            "selected_contract": None,
            "source_unavailable_reason": "historical option source unavailable at replay signal timestamp",
        }
    if option_candidates:
        _validate_option_candidates_point_in_time(
            target=target,
            timestamp=timestamp,
            option_candidates=option_candidates,
        )
        generators = _trading_model_generators()
        unified_decision = _as_mapping(layer_outputs["unified_decision_vector"])
        direct_intent = _as_mapping(layer_outputs["direct_underlying_intent"])
        model_row = generators["model_05_option_expression"](
            [
                {
                    "available_time": timestamp,
                    "tradeable_time": timestamp,
                    "target_candidate_id": layer_outputs["target_candidate_id"],
                    "unified_decision_vector_ref": unified_decision.get("model_ref"),
                    "unified_decision_vector": unified_decision,
                    "direct_underlying_intent": direct_intent,
                    "model_05_underlying_handoff": direct_intent.get("handoff_to_model_05") or {},
                    "market_context_state": layer_outputs["market_context_state"],
                    "event_state_vector": layer_outputs["event_state_vector"],
                    "option_expression_policy": {},
                    "option_contract_candidates": list(option_candidates),
                    "option_surface_status": "optionable_chain_available",
                    "option_chain_snapshot_ref": f"m05_option_expression_feature_generation:{target}:{_time_key(timestamp)}",
                    "option_quote_available_time": timestamp,
                    "underlying_quote_snapshot_ref": _as_mapping(layer_outputs["target_context_state"]).get("model_ref"),
                    "underlying_reference_price": bar.get("bar_close"),
                }
            ]
        )[0]
        plan = dict(model_row["option_expression_plan"])
        selected_contract = _as_mapping(plan.get("selected_contract"))
        plan.update(
            {
                "model_ref": f"{candidate_model_ref}/model_05_option_expression/{model_row['option_expression_plan_ref']}",
                "target_ref": target,
                "asset_expression_route": "listed_option_contract" if selected_contract else "option_expression_unfilled",
                "option_surface_status": model_row.get("option_surface_status") or "optionable_chain_available",
            }
        )
        return plan
    raise ValueError(
        _replay_option_feature_acquisition_message(
            [_replay_option_feature_requirement_sample(target=target, timestamp=timestamp)]
        )
    )


def _replay_option_feature_requirement_sample(*, target: str, timestamp: str) -> dict[str, str]:
    return {
        "target_ref": str(target).upper(),
        "timestamp": timestamp,
        "maximum_permitted_source_end": timestamp,
        "signal_source": "model_04_unified_decision.direct_underlying_intent.handoff_to_model_05",
    }


def _replay_option_feature_acquisition_error(
    requirements: Sequence[Mapping[str, str]],
    *,
    artifact_ref: Path | None = None,
) -> ValueError:
    return ValueError(_replay_option_feature_acquisition_message(requirements, artifact_ref=artifact_ref))


def _write_replay_option_feature_requirements(
    *,
    path: Path | None,
    requirements: Sequence[Mapping[str, str]],
) -> str | None:
    if path is None:
        return None
    deduped = _deduped_replay_option_feature_requirements(requirements)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in deduped:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    return str(path)


def _deduped_replay_option_feature_requirements(
    requirements: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in requirements:
        target = str(item.get("target_ref") or "").upper()
        timestamp = str(item.get("timestamp") or item.get("maximum_permitted_source_end") or "")
        if not target or not timestamp:
            continue
        key = (target, timestamp)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_replay_option_feature_requirement_sample(target=target, timestamp=timestamp))
    return deduped


def _replay_option_feature_acquisition_message(
    requirements: Sequence[Mapping[str, str]],
    *,
    artifact_ref: Path | str | None = None,
) -> str:
    deduped = _deduped_replay_option_feature_requirements(requirements)
    sample = deduped[:REPLAY_OPTION_FEATURE_MISSING_SAMPLE_LIMIT]
    payload: dict[str, Any] = {
        "missing_count": len(deduped),
        "sample": sample,
        "sample_limit": REPLAY_OPTION_FEATURE_MISSING_SAMPLE_LIMIT,
        "required_next_step": "run ThetaData option acquisition only for emitted replay signal timestamps, generate M05 option features, then retry replay execution from the same replay clock",
        "point_in_time_policy": "option provider acquisition for replay must not request or consume data after each replay_time_pointer that emitted an option-expression signal",
    }
    if artifact_ref:
        payload["requirements_artifact_ref"] = str(artifact_ref)
    return REPLAY_OPTION_FEATURE_ACQUISITION_REQUIRED + ": " + json.dumps(payload, sort_keys=True)


def _option_expression_signal_required(layer_outputs: Mapping[str, Any]) -> bool:
    plan = _as_mapping(layer_outputs.get("direct_underlying_intent"))
    action_type = str(plan.get("underlying_action_type") or plan.get("planned_underlying_action_type") or "").lower()
    if action_type not in OPTION_EXPRESSION_SIGNAL_ACTION_TYPES:
        return False
    handoff = _as_mapping(plan.get("handoff_to_model_05"))
    direction = str(handoff.get("underlying_path_direction") or plan.get("action_side") or "").lower()
    if not handoff or direction not in {"bullish", "long"}:
        return False
    if str(plan.get("action_side") or "").lower() != "long":
        return False
    entry_style = str(plan.get("entry_style") or handoff.get("entry_price_assumption") or "").lower()
    if entry_style not in OPTION_EXPRESSION_CURRENT_ENTRY_STYLES:
        return False

    diagnostics = _as_mapping(layer_outputs.get("model_layer_diagnostics"))
    thresholds = _as_mapping(diagnostics.get("entry_thresholds"))
    unified_decision = _as_mapping(layer_outputs.get("unified_decision_vector"))
    alpha_score = (
        _safe_float(layer_outputs.get("prediction_score"))
        or _safe_float(unified_decision.get("unified_decision_confidence_score"))
        or 0.0
    )
    minimum_alpha = (
        _safe_float(thresholds.get("minimum_entry_alpha_confidence"))
        or _safe_float(unified_decision.get("minimum_entry_confidence"))
        or DEFAULT_ENTRY_ALPHA_THRESHOLD
    )
    if alpha_score < minimum_alpha:
        return False

    alpha_diagnostics = _as_mapping(diagnostics.get("model_05_alpha_confidence"))
    if str(alpha_diagnostics.get("alpha_gate_status") or "passed") != "passed":
        return False

    layer4 = _as_mapping(diagnostics.get("model_04_unified_decision"))
    dominant = _as_mapping(layer4.get("dominant_horizon_scores"))
    trade_intensity = _safe_float(dominant.get("trade_intensity_score")) or _safe_float(plan.get("trade_intensity_score")) or 0.0
    minimum_trade_intensity = (
        _safe_float(dominant.get("minimum_trade_intensity"))
        or _safe_float(thresholds.get("minimum_trade_intensity"))
        or DEFAULT_MINIMUM_TRADE_INTENSITY
    )
    if trade_intensity < minimum_trade_intensity:
        return False
    if (_safe_float(dominant.get("action_direction_score")) or 0.0) <= 0.0:
        return False
    if (_safe_float(dominant.get("expected_return_score")) or 0.0) <= 0.0:
        return False
    return True


def _option_source_unavailable(option_candidates: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        str(candidate.get("option_surface_status") or "") == OPTION_SOURCE_UNAVAILABLE_STATUS
        or str(candidate.get("snapshot_type") or "") == OPTION_SOURCE_UNAVAILABLE_SNAPSHOT_TYPE
        or str(candidate.get("option_symbol") or "") == OPTION_SOURCE_UNAVAILABLE_SYMBOL
        for candidate in option_candidates
    )


def _replay_market_snapshot(
    *,
    bar: Mapping[str, Any],
    target: str,
    date_text: str,
    option_expression_plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    selected_contract = _as_mapping(_as_mapping(option_expression_plan).get("selected_contract"))
    option_mid = _safe_float(selected_contract.get("mid_price"))
    if option_mid is not None and option_mid > 0:
        contract_ref = str(selected_contract.get("contract_ref") or selected_contract.get("option_symbol") or target)
        return {
            "market_snapshot_ref": f"storage://replay/option_expression/{target}/{contract_ref}/{date_text}",
            "reference_price": option_mid,
            "close_price": option_mid,
            "underlying_reference_price": float(bar["bar_close"]),
        }
    reference_price = float(bar["bar_close"])
    return {
        "market_snapshot_ref": f"storage://replay/{bar.get('source_id', 'market')}/{target}/{date_text}",
        "reference_price": reference_price,
        "close_price": reference_price,
    }


def _option_contract_path_return(
    *,
    selected_option_contract_ref: str,
    entry_timestamp: str,
    exit_timestamp: str,
    option_contract_paths_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, float] | None:
    rows = list(option_contract_paths_by_symbol.get(str(selected_option_contract_ref).upper(), ()))
    if not rows:
        return None
    entry_row = _first_row_at_or_after(rows, entry_timestamp)
    exit_row = _last_row_at_or_before(rows, exit_timestamp) or _first_row_at_or_after(rows, exit_timestamp)
    if not entry_row or not exit_row:
        return None
    entry_price = _safe_float(entry_row.get("bar_close"))
    exit_price = _safe_float(exit_row.get("bar_close"))
    if entry_price is None or exit_price is None or entry_price <= 0:
        return None
    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "gross_return": (exit_price - entry_price) / entry_price,
    }


def _first_row_at_or_after(rows: Sequence[Mapping[str, Any]], timestamp: str) -> Mapping[str, Any] | None:
    target = _timestamp_sort_key(timestamp)
    for row in rows:
        row_key = _timestamp_sort_key(row.get("timestamp"))
        if row_key >= target:
            return row
    return None


def _last_row_at_or_before(rows: Sequence[Mapping[str, Any]], timestamp: str) -> Mapping[str, Any] | None:
    target = _timestamp_sort_key(timestamp)
    selected: Mapping[str, Any] | None = None
    for row in rows:
        row_key = _timestamp_sort_key(row.get("timestamp"))
        if row_key <= target:
            selected = row
        else:
            break
    return selected


def _option_replay_coverage_summary(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    option_candidates_by_underlying_time: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    option_contract_paths_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    decision_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    option_signal_times = {
        (str(row.get("target_ref") or "").upper(), str(row.get("replay_time_pointer") or ""))
        for row in decision_rows
        if str(row.get("asset_expression_route") or "").strip()
    }
    option_signal_times = {(target, timestamp) for target, timestamp in option_signal_times if target and timestamp}
    selected_option_rows = [row for row in decision_rows if row.get("selected_option_contract_ref")]
    path_available_count = sum(1 for row in selected_option_rows if row.get("option_contract_path_status") == "available")
    path_missing_count = sum(1 for row in selected_option_rows if row.get("option_contract_path_status") == "missing")
    expected_snapshot_count = len(option_signal_times)
    feature_snapshot_count = sum(1 for key in option_signal_times if option_candidates_by_underlying_time.get(key))
    feature_missing_count = max(0, expected_snapshot_count - feature_snapshot_count)
    feature_coverage_ratio = feature_snapshot_count / expected_snapshot_count if expected_snapshot_count else None
    if expected_snapshot_count == 0:
        feature_status = "not_applicable"
    elif feature_snapshot_count >= expected_snapshot_count:
        feature_status = "complete"
    elif feature_snapshot_count > 0:
        feature_status = "partial"
    else:
        feature_status = "missing"
    if not selected_option_rows:
        path_status = "not_applicable"
    elif path_missing_count == 0:
        path_status = "complete"
    elif path_available_count > 0:
        path_status = "partial"
    else:
        path_status = "missing"
    return {
        "feature_snapshot_coverage_status": feature_status,
        "feature_snapshot_count": feature_snapshot_count,
        "expected_option_signal_snapshot_count": expected_snapshot_count,
        "expected_equity_decision_snapshot_count": expected_snapshot_count,
        "expected_equity_target_date_snapshot_count": expected_snapshot_count,
        "missing_equity_decision_snapshot_count": feature_missing_count,
        "feature_snapshot_coverage_ratio": feature_coverage_ratio,
        "contract_path_coverage_status": path_status,
        "contract_path_symbol_count": len(option_contract_paths_by_symbol),
        "contract_path_bar_count": sum(len(rows) for rows in option_contract_paths_by_symbol.values()),
        "selected_option_decision_count": len(selected_option_rows),
        "selected_option_path_available_count": path_available_count,
        "selected_option_path_missing_count": path_missing_count,
    }


def _replay_time_pointer_policy() -> dict[str, Any]:
    return {
        "policy_ref": REPLAY_TIME_POINTER_POLICY_REF,
        "pointer_field": "replay_time_pointer",
        "rule": "decision inputs must have available_time less than or equal to replay_time_pointer",
        "settlement_exception": "future bars and selected-contract path rows may be used only after the decision row is emitted for labels, fills, and realized-return settlement",
    }


def _replay_time_pointer_for_bar(bar: Mapping[str, Any]) -> str:
    return _time_key(bar.get("replay_time_pointer") or bar.get("timestamp"))


def _validate_option_candidates_point_in_time(
    *,
    target: str,
    timestamp: str,
    option_candidates: Sequence[Mapping[str, Any]],
) -> None:
    decision_time = _timestamp_sort_key(timestamp)
    if decision_time <= 0:
        return
    violations: list[dict[str, str]] = []
    for index, candidate in enumerate(option_candidates):
        contract_ref = str(candidate.get("contract_ref") or candidate.get("option_symbol") or f"candidate_{index}")
        for field in OPTION_CANDIDATE_POINT_IN_TIME_FIELDS:
            value = candidate.get(field)
            if value in (None, ""):
                continue
            value_time = _timestamp_sort_key(value)
            if value_time > decision_time:
                violations.append(
                    {
                        "target_ref": target,
                        "timestamp": timestamp,
                        "contract_ref": contract_ref,
                        "field": field,
                        "field_value": str(value),
                    }
                )
                break
            if len(violations) >= OPTION_CANDIDATE_POINT_IN_TIME_SAMPLE_LIMIT:
                break
    if violations:
        raise ValueError(
            REPLAY_OPTION_FEATURE_FUTURE_DATA_REJECTED
            + ": "
            + json.dumps(
                {
                    "violation_count": len(violations),
                    "sample": violations,
                    "point_in_time_policy": "replay option-expression decisions may consume only option candidate evidence available at or before replay_time_pointer",
                },
                sort_keys=True,
            )
        )


def _asset_class_counts(bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rows in bars_by_target.values():
        asset_class = str(rows[0].get("asset_class") or "unknown") if rows else "unknown"
        counts[asset_class] = counts.get(asset_class, 0) + 1
    return counts


def _latest_succeeded_outputs(receipt: Mapping[str, Any]) -> list[str]:
    runs = receipt.get("runs")
    if not isinstance(runs, list):
        return []
    succeeded = [run for run in runs if isinstance(run, Mapping) and run.get("status") == "succeeded"]
    if not succeeded:
        return []
    outputs = succeeded[-1].get("outputs")
    return [str(item) for item in outputs] if isinstance(outputs, list) else []


def _read_bar_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            parsed = dict(row)
            parsed["date"] = str(parsed["timestamp"]).split("T", 1)[0]
            for field in ("bar_open", "bar_high", "bar_low", "bar_close", "bar_volume"):
                parsed[field] = float(parsed[field])
            rows.append(parsed)
        return rows


def _candidate_layer_outputs(
    *,
    target: str,
    target_rows: Sequence[Mapping[str, Any]],
    index: int,
    market_universe: Sequence[Mapping[str, Any]],
    reference_price: float,
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    entry_calibration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    generators = _trading_model_generators()
    available_time = str(target_rows[index]["timestamp"])
    target_candidate_id = _target_candidate_id(target=target, available_time=available_time, candidate_model_ref=candidate_model_ref)
    market_state = _market_context_state(market_universe=market_universe, candidate_model_ref=candidate_model_ref, available_time=available_time)
    sector_state = _sector_context_state(candidate_model_ref=candidate_model_ref, available_time=available_time)
    target_state = _target_context_state(
        target=target,
        rows=target_rows,
        index=index,
        target_candidate_id=target_candidate_id,
        candidate_model_ref=candidate_model_ref,
        reference_price=reference_price,
    )
    event_state = _event_state_vector(candidate_model_ref=candidate_model_ref, available_time=available_time)
    quality_state = _quality_calibration_state()
    event_failure_row = _generate_model_rows(
        generators["model_04_event_failure_risk"],
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "market_context_state_ref": market_state.get("model_ref"),
                "sector_context_state_ref": sector_state.get("model_ref"),
                "target_context_state_ref": target_state.get("model_ref"),
                "market_context_state": market_state,
                "sector_context_state": sector_state,
                "target_context_state": target_state,
                "event_context_vector": event_state,
            }
        ],
        validate_output=False,
    )[0]
    event_failure_vector = dict(_as_mapping(event_failure_row.get("event_failure_risk_vector")))
    event_failure_vector["model_ref"] = f"{candidate_model_ref}/model_04_event_failure_risk/{event_failure_row['event_failure_risk_vector_ref']}"
    alpha_row = _generate_model_rows(
        generators["model_05_alpha_confidence"],
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "market_context_state_ref": market_state.get("model_ref"),
                "sector_context_state_ref": sector_state.get("model_ref"),
                "target_context_state_ref": target_state.get("model_ref"),
                "event_failure_risk_vector_ref": event_failure_row["event_failure_risk_vector_ref"],
                "market_context_state": market_state,
                "sector_context_state": sector_state,
                "target_context_state": target_state,
                "event_failure_risk_vector": event_failure_vector,
                "quality_calibration_state": quality_state,
            }
        ],
        after_cost_alpha_model=after_cost_alpha_model,
        validate_output=False,
    )[0]
    alpha_vector = dict(_as_mapping(alpha_row.get("alpha_confidence_vector")))
    alpha_score = _resolved_alpha_score(alpha_vector)

    policy_gate_state = _entry_policy_gate_state(entry_calibration, alpha_score=alpha_score)
    unified_row = _generate_model_rows(
        generators["model_04_unified_decision"],
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "background_context_state": market_state,
                "sector_context_state": sector_state,
                "target_context_state": target_state,
                "event_state_vector": event_failure_vector,
                "quality_calibration_state": quality_state,
                "portfolio_exposure_state": _flat_portfolio_state(),
                "account_capacity_state": _account_capacity_state(),
                "current_underlying_position_state": {"current_underlying_exposure_score": 0.0},
                "pending_underlying_order_state": {"pending_underlying_exposure_score": 0.0, "pending_fill_probability_estimate": 0.0},
                "underlying_quote_state": {"reference_price": reference_price, "last_price": reference_price, "halt_status": "active"},
                "underlying_liquidity_state": {"spread_bps": 10.0, "dollar_volume": _dollar_volume(target_rows[index])},
                "underlying_borrow_state": {"short_allowed": False},
                "risk_budget_state": {"risk_budget_fit_score": 0.75},
                "policy_gate_state": policy_gate_state,
            }
        ],
        validate_output=False,
    )[0]
    unified_decision = _execution_unified_decision_vector(
        unified_row=unified_row,
        candidate_model_ref=candidate_model_ref,
        reference_price=reference_price,
        entry_calibration=entry_calibration,
        alpha_score=alpha_score,
    )
    direct_intent = dict(unified_row["direct_underlying_intent"])
    direct_intent["model_ref"] = unified_decision["model_ref"]
    target_state_for_execution = dict(target_state)
    target_state_for_execution.update({"current_price": reference_price, "last_price": reference_price, "mark_price": reference_price})
    return {
        "target_candidate_id": target_candidate_id,
        "available_time": available_time,
        "market_context_state": market_state,
        "target_context_state": target_state_for_execution,
        "event_state_vector": event_failure_vector,
        "unified_decision_vector": unified_decision,
        "direct_underlying_intent": direct_intent,
        "prediction_score": alpha_score,
        "model_layer_refs": {
            "model_04_event_failure_risk": event_failure_row["event_failure_risk_vector_ref"],
            "model_05_alpha_confidence": alpha_row["alpha_confidence_vector_ref"],
            "model_04_unified_decision": unified_row["unified_decision_vector_ref"],
        },
        "model_layer_diagnostics": _model_layer_diagnostics(
            unified_row=unified_row,
            unified_decision=unified_decision,
            event_failure_row=event_failure_row,
            alpha_row=alpha_row,
            alpha_score=alpha_score,
            entry_calibration=entry_calibration,
        ),
    }


@lru_cache(maxsize=1)
def _trading_model_generators() -> dict[str, Callable[..., list[dict[str, Any]]]]:
    try:
        from models.model_04_event_failure_risk.generator import generate_rows as generate_event_failure_risk
        from models.model_04_unified_decision.generator import generate_rows as generate_unified_decision
        from models.model_05_alpha_confidence.generator import generate_rows as generate_alpha_confidence
        from models.model_05_option_expression.generator import generate_rows as generate_option_expression
        from models.model_06_residual_event_governance.generator import generate_rows as generate_residual_event_governance
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "trading-model must be importable for model-group replay inference; "
            "include /root/projects/trading-model/src on PYTHONPATH"
        ) from exc
    return {
        "model_04_event_failure_risk": generate_event_failure_risk,
        "model_04_unified_decision": generate_unified_decision,
        "model_05_alpha_confidence": generate_alpha_confidence,
        "model_05_option_expression": generate_option_expression,
        "model_06_residual_event_governance": generate_residual_event_governance,
    }


def _generate_model_rows(
    generator: Callable[..., list[dict[str, Any]]],
    rows: Sequence[Mapping[str, Any]],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    cache_key = id(generator)
    accepted = _GENERATOR_PARAMETER_CACHE.get(cache_key)
    if accepted is None:
        accepted = set(inspect.signature(generator).parameters)
        _GENERATOR_PARAMETER_CACHE[cache_key] = accepted
    filtered_kwargs = {key: value for key, value in kwargs.items() if key in accepted}
    return generator(rows, **filtered_kwargs)


def _selected_entry_thresholds(entry_calibration: Mapping[str, Any] | None) -> dict[str, float]:
    selected = _as_mapping(entry_calibration.get("selected_thresholds") if entry_calibration else None)
    minimum_entry_alpha = _safe_float(selected.get("minimum_entry_alpha_confidence"))
    minimum_trade_intensity = _safe_float(selected.get("minimum_trade_intensity"))
    return {
        "minimum_entry_alpha_confidence": minimum_entry_alpha if minimum_entry_alpha is not None else DEFAULT_ENTRY_ALPHA_THRESHOLD,
        "minimum_trade_intensity": minimum_trade_intensity if minimum_trade_intensity is not None else DEFAULT_MINIMUM_TRADE_INTENSITY,
    }


def _raw_entry_calibration() -> dict[str, Any]:
    return {
        "calibration_status": "raw_candidate_observation",
        "selected_thresholds": {
            "minimum_entry_alpha_confidence": 0.0,
            "minimum_trade_intensity": 0.0,
        },
    }


def _entry_policy_gate_state(entry_calibration: Mapping[str, Any] | None, *, alpha_score: float) -> dict[str, Any]:
    selected = _selected_entry_thresholds(entry_calibration)
    output = {
        "minimum_entry_alpha_confidence": selected["minimum_entry_alpha_confidence"],
        "minimum_trade_intensity": selected["minimum_trade_intensity"],
        "after_cost_alpha_score": alpha_score,
        "entry_threshold_calibration_status": str((entry_calibration or {}).get("calibration_status") or "uncalibrated_default"),
    }
    if alpha_score < selected["minimum_entry_alpha_confidence"]:
        output.update(
            {
                "allow_new_exposure": "false",
                "new_exposure_permission_score": 0.0,
                "alpha_confidence_gate_status": "below_entry_threshold",
            }
        )
    else:
        output["alpha_confidence_gate_status"] = "passed"
    return output


def _entry_calibration_role(*, timestamp: str, entry_calibration: Mapping[str, Any]) -> str:
    replay_month = timestamp[:7]
    validation_months = {
        str(month)
        for month in entry_calibration.get("validation_months", [])
        if isinstance(month, (str, int, float))
    }
    return "validation" if replay_month in validation_months else "test"


def _model_layer_diagnostics(
    *,
    unified_row: Mapping[str, Any],
    unified_decision: Mapping[str, Any],
    event_failure_row: Mapping[str, Any],
    alpha_row: Mapping[str, Any],
    alpha_score: float,
    entry_calibration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    vector = _as_mapping(unified_row.get("unified_decision_vector"))
    direct_intent = _as_mapping(unified_row.get("direct_underlying_intent"))
    diagnostics = _as_mapping(unified_row.get("unified_decision_diagnostics"))
    dominant_horizon = str(vector.get("4_resolved_decision_horizon") or direct_intent.get("dominant_horizon") or "1D")
    dominant_suffix = dominant_horizon if dominant_horizon in {"1D", "1W"} else {"10min": "10min", "1h": "1h"}.get(dominant_horizon, "1D")
    horizon_scores = _as_mapping(diagnostics.get("horizon_decisions") or diagnostics.get("horizon_scores"))
    dominant_scores = _as_mapping(horizon_scores.get(dominant_horizon))
    selected_thresholds = _selected_entry_thresholds(entry_calibration)
    return {
        "entry_thresholds": selected_thresholds,
        "model_04_event_failure_risk": {
            "event_failure_risk_vector_ref": event_failure_row.get("event_failure_risk_vector_ref"),
            "resolved_event_failure_risk_status": event_failure_row.get("4_resolved_event_failure_risk_status"),
            "reason_codes": _as_mapping(event_failure_row.get("event_failure_risk_diagnostics")).get("horizon_reason_codes") or {},
        },
        "model_05_alpha_confidence": {
            "alpha_confidence_vector_ref": alpha_row.get("alpha_confidence_vector_ref"),
            "resolved_alpha_score": alpha_score,
            "alpha_gate_status": "passed"
            if alpha_score >= _selected_entry_thresholds(entry_calibration)["minimum_entry_alpha_confidence"]
            else "below_entry_threshold",
            "horizon_scores": _as_mapping(_as_mapping(alpha_row.get("alpha_confidence_diagnostics")).get("after_cost_alpha_score")),
        },
        "model_04_unified_decision": {
            "resolved_underlying_action_type": direct_intent.get("underlying_action_type")
            or vector.get("4_resolved_underlying_action_type"),
            "resolved_action_side": direct_intent.get("action_side") or vector.get("4_resolved_action_side"),
            "dominant_horizon": dominant_horizon,
            "reason_codes": direct_intent.get("reason_codes") or vector.get("4_resolved_reason_codes") or [],
            "hard_gate_reason_codes": diagnostics.get("hard_gate_reason_codes") or [],
            "dominant_horizon_scores": {
                "trade_intensity_score": _first_float(
                    dominant_scores.get("trade_intensity_score"),
                    vector.get(f"4_trade_intensity_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "minimum_trade_intensity": _first_float(
                    dominant_scores.get("minimum_trade_intensity"),
                    selected_thresholds["minimum_trade_intensity"],
                ),
                "materiality_adjusted_action_score": _first_float(
                    dominant_scores.get("materiality_adjusted_action_score"),
                    vector.get(f"4_materiality_adjusted_action_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "no_trade_probability_score": _first_float(
                    dominant_scores.get("no_trade_probability_score"),
                    vector.get(f"4_no_trade_probability_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "entry_quality_score": _first_float(dominant_scores.get("entry_quality_score"), default=0.0),
                "action_confidence_score": _first_float(
                    dominant_scores.get("action_confidence_score"),
                    unified_decision.get("unified_decision_confidence_score"),
                    default=0.0,
                ),
                "action_direction_score": _first_float(
                    dominant_scores.get("action_direction_score"),
                    vector.get(f"4_action_direction_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "expected_return_score": _first_float(
                    dominant_scores.get("expected_return_score"),
                    vector.get(f"4_expected_return_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "downside_risk_score": _first_float(
                    dominant_scores.get("downside_risk_score"),
                    vector.get(f"4_downside_risk_score_{dominant_suffix}"),
                    default=0.0,
                ),
                "minimum_entry_alpha_confidence": _first_float(
                    dominant_scores.get("minimum_entry_alpha_confidence"),
                    selected_thresholds["minimum_entry_alpha_confidence"],
                ),
            },
        },
    }


def _target_candidate_id(*, target: str, available_time: str, candidate_model_ref: str) -> str:
    token = f"{candidate_model_ref}:{target}:{available_time}".encode("utf-8")
    import hashlib

    return f"replay_{target.lower()}_{hashlib.sha256(token).hexdigest()[:16]}"


def _market_context_state(*, market_universe: Sequence[Mapping[str, Any]], candidate_model_ref: str, available_time: str) -> dict[str, Any]:
    prices = [float(row["reference_price"]) for row in market_universe if row.get("reference_price") is not None]
    dispersion = 0.0
    if prices:
        mean_price = sum(prices) / len(prices)
        dispersion = 0.0 if mean_price <= 0 else min(max((max(prices) - min(prices)) / mean_price, 0.0), 1.0)
    return {
        "model_ref": f"{candidate_model_ref}/model_01_market_regime_state/{available_time}",
        "1_market_risk_stress_score": min(0.25 + dispersion * 0.2, 0.75),
        "1_market_liquidity_support_score": 0.75,
        "1_transition_risk_score": min(0.20 + dispersion * 0.15, 0.70),
        "1_state_quality_score": 0.70,
    }


def _sector_context_state(*, candidate_model_ref: str, available_time: str) -> dict[str, Any]:
    return {
        "model_ref": f"{candidate_model_ref}/model_02_sector_context_state/{available_time}",
        "2_sector_context_support_quality_score": 0.60,
        "2_state_quality_score": 0.70,
    }


def _target_context_state(
    *,
    target: str,
    rows: Sequence[Mapping[str, Any]],
    index: int,
    target_candidate_id: str,
    candidate_model_ref: str,
    reference_price: float,
) -> dict[str, Any]:
    momentum_7d = _window_return(rows, index, 7)
    momentum_30d = _window_return(rows, index, 30)
    daily = _daily_return(rows, index)
    direction_1d = _clip_signed(daily * 8.0 + momentum_7d * 3.0)
    direction_1w = _clip_signed(momentum_7d * 4.0 + momentum_30d)
    trend_quality = _clip01(0.5 + abs(momentum_7d) * 8.0 + abs(momentum_30d) * 2.0)
    liquidity = _volume_rank(rows, index, 30)
    return {
        "model_ref": f"{candidate_model_ref}/model_03_target_state_vector/{target_candidate_id}",
        "target_ref": target,
        "target_candidate_id": target_candidate_id,
        "3_target_direction_score_10min": direction_1d,
        "3_target_direction_score_1h": direction_1d,
        "3_target_direction_score_1D": direction_1d,
        "3_target_direction_score_1W": direction_1w,
        "3_target_trend_quality_score_10min": trend_quality,
        "3_target_trend_quality_score_1h": trend_quality,
        "3_target_trend_quality_score_1D": trend_quality,
        "3_target_trend_quality_score_1W": trend_quality,
        "3_target_path_stability_score_10min": _clip01(0.65 - abs(daily) * 4.0),
        "3_target_path_stability_score_1h": _clip01(0.65 - abs(daily) * 4.0),
        "3_target_path_stability_score_1D": _clip01(0.65 - abs(daily) * 4.0),
        "3_target_path_stability_score_1W": _clip01(0.65 - abs(momentum_7d) * 2.0),
        "3_target_noise_score_10min": _clip01(abs(daily) * 4.0),
        "3_target_noise_score_1h": _clip01(abs(daily) * 4.0),
        "3_target_noise_score_1D": _clip01(abs(daily) * 4.0),
        "3_target_noise_score_1W": _clip01(abs(momentum_7d) * 2.0),
        "3_target_transition_risk_score_10min": _clip01(abs(daily - momentum_7d) * 2.0),
        "3_target_transition_risk_score_1h": _clip01(abs(daily - momentum_7d) * 2.0),
        "3_target_transition_risk_score_1D": _clip01(abs(daily - momentum_7d) * 2.0),
        "3_target_transition_risk_score_1W": _clip01(abs(momentum_7d - momentum_30d) * 2.0),
        "3_context_direction_alignment_score_10min": direction_1d,
        "3_context_direction_alignment_score_1h": direction_1d,
        "3_context_direction_alignment_score_1D": direction_1d,
        "3_context_direction_alignment_score_1W": direction_1w,
        "3_context_support_quality_score_10min": 0.60,
        "3_context_support_quality_score_1h": 0.60,
        "3_context_support_quality_score_1D": 0.60,
        "3_context_support_quality_score_1W": 0.60,
        "3_tradability_score_10min": liquidity,
        "3_tradability_score_1h": liquidity,
        "3_tradability_score_1D": liquidity,
        "3_tradability_score_1W": liquidity,
        "3_target_liquidity_tradability_score": liquidity,
        "3_state_quality_score": 0.70,
        "current_price": reference_price,
        "last_price": reference_price,
        "mark_price": reference_price,
    }


def _event_state_vector(*, candidate_model_ref: str, available_time: str) -> dict[str, Any]:
    state = {"model_ref": f"{candidate_model_ref}/model_03_event_state/{available_time}"}
    for suffix in ("10min", "1h", "1D", "1W"):
        state.update(
            {
                f"3_event_applicability_confidence_score_{suffix}": 0.0,
                f"3_event_entry_block_pressure_score_{suffix}": 0.0,
                f"3_event_exposure_cap_pressure_score_{suffix}": 0.0,
                f"3_event_strategy_disable_pressure_score_{suffix}": 0.0,
                f"3_event_path_risk_score_{suffix}": 0.0,
                f"3_event_uncertainty_score_{suffix}": 0.0,
                f"3_event_response_direction_score_{suffix}": 0.0,
            }
        )
    return state


def _quality_calibration_state() -> dict[str, float]:
    return {
        "state_neighborhood_sample_count_score": 0.60,
        "state_neighborhood_outcome_stability": 0.55,
        "model_ensemble_agreement_score": 0.60,
        "model_disagreement_score": 0.25,
        "out_of_distribution_score": 0.20,
        "data_quality_score": 0.70,
    }


def _flat_portfolio_state() -> dict[str, float]:
    return {
        "correlation_concentration_score": 0.20,
        "concentration_score": 0.20,
        "gross_exposure_capacity_score": 0.80,
    }


def _account_capacity_state() -> dict[str, float]:
    return {
        "drawdown_pressure_score": 0.10,
        "cash_capacity_score": 0.85,
        "premium_capacity_score": 0.80,
    }


def _execution_unified_decision_vector(
    *,
    unified_row: Mapping[str, Any],
    candidate_model_ref: str,
    reference_price: float,
    entry_calibration: Mapping[str, Any] | None,
    alpha_score: float,
) -> dict[str, Any]:
    vector = dict(_as_mapping(unified_row.get("unified_decision_vector")))
    intent = _as_mapping(unified_row.get("direct_underlying_intent"))
    handoff = _as_mapping(intent.get("handoff_to_model_05"))
    action_side = str(intent.get("action_side") or vector.get("4_resolved_action_side") or "").strip()
    direction = "long" if action_side == "long" else "short" if action_side == "short" else None
    entry_price = _safe_float(handoff.get("expected_entry_price")) or reference_price
    target_price = _safe_float(handoff.get("expected_target_price")) or _safe_float(intent.get("expected_target_price"))
    stop_price = _safe_float(handoff.get("stop_loss_price")) or _safe_float(intent.get("thesis_invalidation_price"))
    invalidation_price = _safe_float(handoff.get("thesis_invalidation_price")) or stop_price
    model_04_confidence = (
        _safe_float(vector.get("4_resolved_action_confidence_score"))
        or _safe_float(vector.get("4_action_confidence_score_1D"))
        or 0.0
    )
    selected = _selected_entry_thresholds(entry_calibration)
    output = dict(vector)
    output.update(
        {
            "model_ref": f"{candidate_model_ref}/model_04_unified_decision/{unified_row['unified_decision_vector_ref']}",
            "unified_decision_vector_ref": unified_row["unified_decision_vector_ref"],
            "unified_decision_confidence_score": alpha_score,
            "model_04_action_confidence_score": model_04_confidence,
            "minimum_entry_confidence": selected["minimum_entry_alpha_confidence"],
            "entry_direction": direction,
            "entry_zone": {
                "low": min(entry_price, reference_price),
                "high": max(entry_price, reference_price),
            },
            "target_price": target_price,
            "model_invalidation_price": invalidation_price,
            "hard_stop_price": stop_price,
            "expected_horizon": intent.get("dominant_horizon") or vector.get("4_resolved_decision_horizon"),
            "current_price": reference_price,
            "reference_price": reference_price,
            "direct_underlying_intent": dict(intent),
        }
    )
    return output


def _residual_event_governance_for_bar(
    *,
    candidate_model_ref: str,
    timestamp: str,
    layer_outputs: Mapping[str, Any],
    option_expression_plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    generators = _trading_model_generators()
    option_plan = _as_mapping(option_expression_plan)
    row = generators["model_06_residual_event_governance"](
        [
            {
                "available_time": timestamp,
                "tradeable_time": timestamp,
                "target_candidate_id": layer_outputs["target_candidate_id"],
                "background_context_state_ref": _as_mapping(layer_outputs["market_context_state"]).get("model_ref"),
                "target_context_state_ref": _as_mapping(layer_outputs["target_context_state"]).get("model_ref"),
                "event_state_vector_ref": _as_mapping(layer_outputs["event_state_vector"]).get("model_ref"),
                "unified_decision_vector_ref": _as_mapping(layer_outputs["unified_decision_vector"]).get("model_ref"),
                "option_expression_plan_ref": option_plan.get("model_ref"),
                "target_context_state": layer_outputs["target_context_state"],
                "unified_decision_vector": layer_outputs["unified_decision_vector"],
                "option_expression_plan": option_plan,
                "residual_event_observations": [],
            }
        ]
    )[0]
    governance = dict(row["event_risk_intervention"])
    governance.update(
        {
            "model_ref": f"{candidate_model_ref}/model_06_residual_event_governance/{row['event_risk_intervention_ref']}",
            "event_risk_intervention_ref": row["event_risk_intervention_ref"],
            "risk_level": "low",
            "block_new_entries": False,
            "halt_new_entries": False,
        }
    )
    return governance


def _resolved_alpha_score(alpha_vector: Mapping[str, Any]) -> float:
    for key in ("5_after_cost_alpha_score_1D", "5_after_cost_alpha_score_1W", "5_after_cost_alpha_score_1h", "5_after_cost_alpha_score_10min"):
        value = _safe_float(alpha_vector.get(key))
        if value is not None:
            return _clip01(value)
    for key in ("5_alpha_confidence_score_1D", "5_alpha_confidence_score_1W", "5_alpha_confidence_score_1h", "5_alpha_confidence_score_10min"):
        value = _safe_float(alpha_vector.get(key))
        if value is not None:
            return _clip01(value)
    return 0.0


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _coerce_json_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _time_key(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return str(value or "")
    return parsed.isoformat()


def _timestamp_sort_key(value: Any) -> float:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _validate_identifier(identifier: str) -> None:
    if not identifier.replace("_", "").isalnum() or not identifier or identifier[0].isdigit():
        raise ValueError(f"unsafe SQL identifier: {identifier!r}")


def _dollar_volume(row: Mapping[str, Any]) -> float:
    close = _safe_float(row.get("bar_close")) or 0.0
    volume = _safe_float(row.get("bar_volume")) or 0.0
    return close * volume


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values: Any, default: float | None = None) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return default


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clip_signed(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _daily_return(rows: Sequence[Mapping[str, Any]], index: int) -> float:
    if index <= 0:
        return 0.0
    previous = float(rows[index - 1]["bar_close"])
    current = float(rows[index]["bar_close"])
    return (current - previous) / previous if previous > 0 else 0.0


def _window_return(rows: Sequence[Mapping[str, Any]], index: int, window: int) -> float:
    if index < window:
        return 0.0
    previous = float(rows[index - window]["bar_close"])
    current = float(rows[index]["bar_close"])
    return (current - previous) / previous if previous > 0 else 0.0


def _volume_rank(rows: Sequence[Mapping[str, Any]], index: int, window: int) -> float:
    start = max(0, index - window + 1)
    volumes = [float(row["bar_volume"]) for row in rows[start : index + 1]]
    if not volumes:
        return 0.0
    current = float(rows[index]["bar_volume"])
    return sum(1 for volume in volumes if volume <= current) / len(volumes)


def _trade_risk_cap(
    reference_price: float,
    *,
    option_expression_plan: Mapping[str, Any] | None = None,
    allocation_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    allocation = _as_mapping(allocation_context)
    minimum_position_notional_usd = _safe_float(allocation.get("target_allocation_notional_usd"))
    if minimum_position_notional_usd is None:
        minimum_position_notional_usd = DEFAULT_REPLAY_INITIAL_CAPITAL_USD * DEFAULT_TARGET_ALLOCATION_FRACTION
    selected_contract = _as_mapping(_as_mapping(option_expression_plan).get("selected_contract"))
    unit_cost = _selected_option_contract_unit_cost(selected_contract) if selected_contract else reference_price
    if unit_cost is None or unit_cost <= 0.0:
        unit_cost = reference_price
    if selected_contract:
        planned_quantity = max(1, math.ceil(minimum_position_notional_usd / unit_cost))
        planned_position_notional = unit_cost * planned_quantity
    else:
        planned_position_notional = minimum_position_notional_usd
        planned_quantity = planned_position_notional / reference_price if reference_price > 0.0 else 1.0
    return {
        "max_loss_usd": max(10.0, reference_price * 0.05),
        "max_loss_pct": 0.02,
        "time_stop_at": "2026-01-01T00:00:00Z",
        "cap_enforcement_mode": "broker_native_stop",
        "cap_failure_action": "reject_order",
        "model_invalidation_price": reference_price * 0.97,
        "hard_stop_price": reference_price * 0.96,
        "planned_quantity": float(planned_quantity),
        "planned_limit_price": reference_price,
        "planned_unit_cost_usd": float(unit_cost),
        "planned_position_notional_usd": float(planned_position_notional),
        "minimum_position_notional_usd": float(minimum_position_notional_usd),
        "target_allocation_fraction": allocation.get("target_allocation_fraction"),
        "target_allocation_fraction_source": allocation.get("target_allocation_fraction_source"),
        "total_portfolio_notional_usd": allocation.get("total_portfolio_notional_usd"),
        "position_sizing_policy": "minimum_notional_floor_option_contract_round_up",
        "sizing_reason_codes": [
            "minimum_position_notional_is_floor_not_cap",
            "single_contract_allowed_above_minimum_notional",
        ],
        **({"estimated_contract_cost_usd": float(unit_cost)} if selected_contract else {}),
    }


def _validate_frozen_dataset(manifest: Mapping[str, Any], freeze_receipt: Mapping[str, Any]) -> None:
    errors: list[str] = []
    if manifest.get("contract_type") != "replay_dataset_preparation_manifest":
        errors.append("dataset manifest contract_type must be replay_dataset_preparation_manifest")
    if freeze_receipt.get("contract_type") != "replay_dataset_freeze_receipt":
        errors.append("replay freeze receipt contract_type must be replay_dataset_freeze_receipt")
    manifest_contract_id = str(manifest.get("contract_id") or "")
    receipt_contract_id = str(freeze_receipt.get("contract_id") or "")
    if manifest_contract_id and receipt_contract_id and manifest_contract_id != receipt_contract_id:
        errors.append("dataset manifest and freeze receipt contract_id must match")
    if not freeze_receipt.get("dataset_manifest_ref"):
        errors.append("replay freeze receipt dataset_manifest_ref is required")
    if not freeze_receipt.get("coverage_summary_ref"):
        errors.append("replay freeze receipt coverage_summary_ref is required")
    if manifest.get("freeze_status") != "frozen":
        errors.append("dataset manifest freeze_status must be frozen")
    if freeze_receipt.get("freeze_status") != "frozen":
        errors.append("replay freeze receipt freeze_status must be frozen")
    validation = freeze_receipt.get("validation")
    if not isinstance(validation, Mapping) or validation.get("validation_status") != "passed":
        errors.append("replay freeze receipt validation_status must be passed")
    if int(manifest.get("missing_feed_acquisition_count", -1)) != 0:
        errors.append("dataset manifest missing_feed_acquisition_count must be 0")
    if not _string_set(manifest.get("pre_replay_target_refs")):
        errors.append("dataset manifest pre_replay_target_refs must include at least one Layer 1/2 base context target")
    safety = freeze_receipt.get("safety")
    if not isinstance(safety, Mapping):
        errors.append("replay freeze receipt safety is required")
    else:
        if safety.get("provider_calls_performed") is not False:
            errors.append("replay freeze receipt must prove no provider calls")
        if safety.get("broker_execution_performed") is not False:
            errors.append("replay freeze receipt must prove no broker execution")
        if safety.get("account_mutation_performed") is not False:
            errors.append("replay freeze receipt must prove no account mutation")
    if errors:
        raise ValueError("; ".join(errors))


def _validate_replay_month_coverage(*, plan_path: Path, replay_month: str) -> None:
    rows: list[dict[str, str]] = []
    with plan_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("month") == replay_month:
                rows.append(dict(row))
    if not rows:
        raise ValueError(f"replay month {replay_month} has no feed acquisition rows")
    unavailable = [
        f"{row.get('source_id')}:{row.get('coverage_status')}"
        for row in rows
        if row.get("coverage_status") != "available"
    ]
    if unavailable:
        raise ValueError(f"replay month {replay_month} source coverage is incomplete: {', '.join(unavailable)}")
    expected_sources = {
        "alpaca_bars",
        "alpaca_liquidity",
        "alpaca_news",
        "gdelt_news",
        "trading_economics_calendar_web",
    }
    present_sources = {str(row.get("source_id") or "") for row in rows}
    missing_sources = sorted(expected_sources - present_sources)
    if missing_sources:
        raise ValueError(f"replay month {replay_month} missing required source rows: {', '.join(missing_sources)}")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "CRYPTO_SPOT_ACCOUNT_SLEEVE",
    "PORTFOLIO_TRACE_AUDIT_CONTRACT",
    "PORTFOLIO_TRACE_AUDIT_ROW_CONTRACT",
    "REPLAY_DECISION_ROW_CONTRACT",
    "REPLAY_EXECUTION_RUN_CONTRACT",
    "PortfolioTraceAuditResult",
    "ReplayExecutionResult",
    "build_candidate_policy_portfolio_trace_audit",
    "build_candidate_policy_replay_execution_run",
    "build_crypto_replay_execution_run",
]
