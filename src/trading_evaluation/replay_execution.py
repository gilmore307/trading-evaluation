"""Side-effect-free Replay execution over frozen source artifacts.

This module orchestrates replay decisions through `trading-execution`. It reads
already-frozen local source artifacts and emits evaluation decision rows. It
does not call providers, train models, activate models, call brokers, or mutate
accounts.
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .execution_runtime import EXECUTION_REPLAY_ROUTE_REF, build_replay_runtime_dry_run

REPLAY_EXECUTION_RUN_CONTRACT = "evaluation_replay_execution_run"
REPLAY_DECISION_ROW_CONTRACT = "evaluation_replay_decision_row"
REPLAY_PROGRESS_CONTRACT = "evaluation_replay_progress"
ENTRY_THRESHOLD_CALIBRATION_CONTRACT = "validation_entry_threshold_calibration"
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
MODEL_INFERENCE_CHAIN = (
    "model_01_market_regime_state",
    "model_02_sector_context_state",
    "model_03_target_state_vector_state",
    "model_04_event_failure_risk_state",
    "model_05_alpha_confidence",
    "model_06_dynamic_risk_policy",
    "model_07_position_projection",
    "model_08_underlying_action",
    "model_09_option_expression",
)
DEFAULT_ENTRY_ALPHA_THRESHOLD = 0.50
DEFAULT_MINIMUM_TRADE_INTENSITY = 0.05
REPLAY_COST_PER_FILLED_DECISION = 0.0015
DISALLOWED_PLACEHOLDER_CANDIDATE_MODEL_REFS = (
    "trading-model://candidate_policy_replay/current_deterministic_crypto_policy",
)


@dataclass(frozen=True)
class ReplayExecutionResult:
    """Replay execution receipt and decision-row output paths."""

    receipt_path: Path
    decision_rows_path: Path
    progress_path: Path
    receipt: dict[str, Any]


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
    calibration_window_month_count: int = 1,
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
    calibration_window_month_count: int = 1,
    include_crypto: bool = True,
    include_equity: bool = True,
    equity_source_root: Path = EQUITY_SOURCE_ROOT,
    equity_symbols: Sequence[str] | None = None,
    replay_month: str | None = None,
    option_feature_database_url: str | None = None,
    option_feature_schema: str = "trading_data",
    option_feature_table: str = "m09_option_expression_feature_generation",
    option_contract_path_table: str = "m09_option_expression_data_acquisition_contract_path",
) -> ReplayExecutionResult:
    """Run candidate-policy replay over frozen crypto plus materialized equity bars."""

    candidate_model_ref = _require_candidate_model_ref(candidate_model_ref)
    if after_cost_alpha_model is None:
        raise ValueError("after_cost_alpha_model is required for replay Layer 5 inference")
    manifest = _load_json(dataset_root / "dataset_manifest.json")
    freeze_receipt_path = dataset_root / "replay_freeze_receipt.json"
    freeze_receipt: dict[str, Any] | None = None
    plan_path = Path(str(manifest["feed_acquisition_plan_ref"]))
    if replay_month:
        _validate_replay_month_coverage(plan_path=plan_path, replay_month=replay_month)
    else:
        freeze_receipt = _load_json(freeze_receipt_path)
        _validate_frozen_dataset(manifest, freeze_receipt)
    generated_at = generated_at_utc or _now_utc()
    run_id = run_id or f"candidate_policy_replay_{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    output_dir = output_dir or dataset_root / "replay_execution_runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_rows_path = output_dir / "decision_rows.jsonl"
    receipt_path = output_dir / "replay_execution_receipt.json"
    progress_path = progress_path or dataset_root / "replay_progress.jsonl"
    calibration_path = output_dir / "entry_threshold_calibration.json"

    bars_by_target = _load_candidate_policy_bars(
        plan_path=plan_path,
        include_crypto=include_crypto,
        include_equity=include_equity,
        equity_source_root=equity_source_root,
        equity_symbols=equity_symbols or _manifest_equity_target_refs(manifest),
        replay_month=replay_month,
    )
    if not bars_by_target:
        raise ValueError("candidate-policy replay found no materialized market bars")
    resolved_option_feature_database_url = (
        _default_option_feature_database_url() if option_feature_database_url is None else option_feature_database_url
    )
    option_candidates_by_underlying_time = _load_option_candidate_features(
        database_url=resolved_option_feature_database_url,
        schema=option_feature_schema,
        table=option_feature_table,
        targets=bars_by_target.keys(),
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
    )
    receipt = {
        "contract_type": REPLAY_EXECUTION_RUN_CONTRACT,
        "replay_execution_run_id": run_id,
        "execution_scope": "candidate_policy_replay_materialized_market_data",
        "candidate_model_ref": candidate_model_ref,
        "after_cost_alpha_model_ref": after_cost_alpha_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "replay_route_ref": EXECUTION_REPLAY_ROUTE_REF,
        "candidate_fold_id": str(manifest.get("candidate_fold_id") or manifest.get("fold_id") or ""),
        "tradable_target_refs": sorted(_string_set(manifest.get("tradable_target_refs"))),
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
        "option_feature_table_ref": None if not resolved_option_feature_database_url else f"{option_feature_schema}.{option_feature_table}",
        "option_feature_snapshot_count": len(option_candidates_by_underlying_time),
        "option_feature_candidate_count": sum(len(rows) for rows in option_candidates_by_underlying_time.values()),
        "option_contract_path_table_ref": None if not resolved_option_feature_database_url else f"{option_feature_schema}.{option_contract_path_table}",
        "option_contract_path_symbol_count": len(option_contract_paths_by_symbol),
        "option_contract_path_bar_count": sum(len(rows) for rows in option_contract_paths_by_symbol.values()),
        "option_replay_coverage": option_replay_coverage,
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
            "candidate-policy replay over frozen OKX crypto bars and materialized Alpaca equity bars",
            "equity/options account uses direct-underlying fallback when option surface status is optionable_chain_missing",
            "listed option decisions use M09 selected-contract paths when available and zero realized return when selected-contract exit data is missing",
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


def _require_candidate_model_ref(candidate_model_ref: str) -> str:
    text = str(candidate_model_ref or "").strip()
    if not text:
        raise ValueError("candidate_model_ref is required")
    if text in DISALLOWED_PLACEHOLDER_CANDIDATE_MODEL_REFS:
        raise ValueError("candidate_model_ref must point to a concrete model-group candidate, not the deterministic placeholder")
    return text


def _build_replay_progress_rows(
    *,
    decision_rows: Sequence[Mapping[str, Any]],
    run_id: str,
    generated_at_utc: str,
    receipt_path: Path,
    decision_rows_path: Path,
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
    observations = _entry_calibration_observations(
        bars_by_target=bars_by_target,
        candidate_model_ref=candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        max_decision_rows=max_decision_rows,
    )
    validation_months = sorted({str(row["replay_month"]) for row in observations})[: max(validation_month_count, 1)]
    validation_rows = [row for row in observations if row["replay_month"] in set(validation_months)]
    selected = _select_entry_thresholds(validation_rows)
    artifact = {
        "contract_type": ENTRY_THRESHOLD_CALIBRATION_CONTRACT,
        "candidate_model_ref": candidate_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "generated_at_utc": generated_at_utc,
        "calibration_method": "fixed_layer_5_neutral_score_with_validation_trade_intensity_selection",
        "validation_months": validation_months,
        "validation_observation_count": len(validation_rows),
        "total_observation_count": len(observations),
        "selected_thresholds": selected["thresholds"],
        "selected_metrics": selected["metrics"],
        "calibration_status": selected["status"],
        "candidate_threshold_count": selected["candidate_threshold_count"],
        "notes": [
            "Layer 5 alpha uses the normalized after-cost score boundary: 0.5 is neutral, above 0.5 is positive edge",
            "validation may select Layer 8 trade intensity, but it does not move the Layer 5 economic neutral boundary",
            "selection uses Layer 8 trade intensity, positive expected-return direction, and next-bar validation utility after replay costs",
            "Layer 10 remains post-replay attribution and is not used for same-run entry decisions",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return EntryCalibration(artifact=artifact, path=output_path)


def _entry_calibration_observations(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate_model_ref: str,
    after_cost_alpha_model: Mapping[str, Any],
    max_decision_rows: int | None,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    for target in sorted(history_by_target):
        target_rows = history_by_target[target]
        for index, bar in enumerate(target_rows[:-1]):
            if max_decision_rows is not None and len(observations) >= max_decision_rows:
                return observations
            next_bar = target_rows[index + 1]
            reference_price = float(bar["bar_close"])
            layer_outputs = _candidate_layer_outputs(
                target=target,
                target_rows=target_rows,
                index=index,
                market_universe=_market_universe_for_date(history_by_target, index_by_target_date, str(bar["date"])),
                reference_price=reference_price,
                candidate_model_ref=candidate_model_ref,
                after_cost_alpha_model=after_cost_alpha_model,
                entry_calibration=_raw_entry_calibration(),
            )
            diagnostics = layer_outputs["model_layer_diagnostics"]
            layer8 = diagnostics["model_08_underlying_action"]
            dominant = layer8["dominant_horizon_scores"]
            gross_return = (float(next_bar["bar_close"]) - reference_price) / reference_price
            observations.append(
                {
                    "target_ref": target,
                    "timestamp": bar["timestamp"],
                    "replay_month": str(bar["timestamp"])[:7],
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
    alpha_thresholds = [DEFAULT_ENTRY_ALPHA_THRESHOLD]
    intensity_thresholds = [round(value / 1000.0, 3) for value in range(1, 31)]
    min_trade_count = max(3, math.ceil(len(validation_rows) * 0.02))
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
            "candidate_threshold_count": len(candidates),
        }
    if candidates:
        selected = max(candidates, key=lambda item: (item["objective_score"], item["metrics"]["average_return_after_cost"]))
        return {
            "status": "selected_best_available_nonpositive_validation_threshold",
            "thresholds": selected["thresholds"],
            "metrics": selected["metrics"],
            "candidate_threshold_count": len(candidates),
        }
    return {
        "status": "fallback_no_validation_threshold_candidate",
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
        "candidate_threshold_count": 0,
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
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history_by_target = {target: list(bars) for target, bars in bars_by_target.items()}
    index_by_target_date = {
        target: {str(row["date"]): index for index, row in enumerate(target_rows)}
        for target, target_rows in history_by_target.items()
    }
    for target in sorted(history_by_target):
        target_rows = history_by_target[target]
        for index, bar in enumerate(target_rows[:-1]):
            if max_decision_rows is not None and len(rows) >= max_decision_rows:
                return rows
            next_bar = target_rows[index + 1]
            date_text = str(bar["date"])
            market_universe = _market_universe_for_date(history_by_target, index_by_target_date, date_text)
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
            option_expression_plan = _option_expression_plan_for_bar(
                bar=bar,
                candidate_model_ref=candidate_model_ref,
                timestamp=str(bar["timestamp"]),
                layer_outputs=layer_outputs,
                option_candidates=option_candidates_by_underlying_time.get((target.upper(), _time_key(bar["timestamp"])), ()),
            )
            replay_market_snapshot = _replay_market_snapshot(
                bar=bar,
                target=target,
                date_text=date_text,
                option_expression_plan=option_expression_plan,
            )
            replay_trade_risk_cap = _trade_risk_cap(float(replay_market_snapshot["reference_price"]))
            replay_result = build_replay_runtime_dry_run(
                account_sleeve_id=_account_sleeve_for_bar(bar),
                target_ref=target,
                market_universe=market_universe,
                target_context_state=layer_outputs["target_context_state"],
                event_failure_risk_vector=layer_outputs["event_failure_risk_vector"],
                alpha_confidence_vector=layer_outputs["alpha_confidence_vector"],
                dynamic_risk_policy_state=layer_outputs["dynamic_risk_policy_state"],
                underlying_action_plan=layer_outputs["underlying_action_plan"],
                option_expression_plan=option_expression_plan,
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
            filled = fill.get("fill_status") == "simulated_filled"
            selected_contract = _as_mapping(_as_mapping(option_expression_plan).get("selected_contract"))
            selected_option_contract_ref = str(selected_contract.get("contract_ref") or selected_contract.get("option_symbol") or "")
            asset_class = "us_option" if selected_option_contract_ref else entry.get("asset_class") or bar.get("asset_class")
            option_path_result = _option_contract_path_return(
                selected_option_contract_ref=selected_option_contract_ref,
                entry_timestamp=str(bar["timestamp"]),
                exit_timestamp=str(next_bar["timestamp"]),
                option_contract_paths_by_symbol=option_contract_paths_by_symbol,
            )
            gross_return = (float(next_bar["bar_close"]) - reference_price) / reference_price
            return_source = "underlying_next_bar"
            option_contract_path_status = "not_applicable"
            option_entry_price = option_exit_price = None
            if selected_option_contract_ref:
                if option_path_result:
                    gross_return = float(option_path_result["gross_return"])
                    return_source = "m09_option_expression_contract_path"
                    option_contract_path_status = "available"
                    option_entry_price = option_path_result["entry_price"]
                    option_exit_price = option_path_result["exit_price"]
                else:
                    gross_return = 0.0
                    return_source = "option_contract_path_missing"
                    option_contract_path_status = "missing"
            cost = REPLAY_COST_PER_FILLED_DECISION if filled else 0.0
            realized_return = gross_return if filled else 0.0
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
                    "asset_expression_route": str(_as_mapping(option_expression_plan).get("asset_expression_route") or ""),
                    "option_surface_status": str(_as_mapping(option_expression_plan).get("option_surface_status") or ""),
                    "selected_option_expression_type": _as_mapping(option_expression_plan).get("selected_expression_type"),
                    "selected_option_contract_ref": selected_option_contract_ref or None,
                    "selected_option_mid_price": selected_contract.get("mid_price"),
                    "option_contract_path_status": option_contract_path_status,
                    "option_entry_price": option_entry_price,
                    "option_exit_price": option_exit_price,
                    "return_source": return_source,
                    "timestamp": bar["timestamp"],
                    "next_timestamp": next_bar["timestamp"],
                    "decision_status": entry["decision_status"],
                    "decision_action": entry["decision_action"],
                    "action": entry["decision_action"],
                    "fill_status": fill["fill_status"],
                    "prediction_score": layer_outputs["prediction_score"],
                    "outcome_label": 1 if gross_return > 0 else 0,
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
                    "model_inference_chain": list(MODEL_INFERENCE_CHAIN),
                    "model_inference_mode": "trading_model_layer_generators",
                    "model_layer_refs": layer_outputs["model_layer_refs"],
                    "model_layer_diagnostics": layer_outputs["model_layer_diagnostics"],
                    "validation_status": replay_result["validation_status"],
                    "side_effects": replay_result["side_effects"],
                }
            )
    return rows


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
        equity_rows = (
            _load_equity_bars_from_plan(plan_path=plan_path, replay_month=replay_month, equity_symbols=equity_symbols)
            if replay_month
            else _load_equity_bars(equity_source_root=equity_source_root, equity_symbols=equity_symbols)
        )
        for target, rows in equity_rows.items():
            if rows:
                rows_by_target[target] = rows
    return rows_by_target


def _manifest_equity_target_refs(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    refs = _string_set(manifest.get("tradable_target_refs"))
    return tuple(sorted(ref for ref in refs if ref not in CRYPTO_SYMBOLS_BY_INSTRUMENT.values()))


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return {stripped.upper()} if stripped else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().upper() for item in value if str(item).strip()}
    return set()


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
                  AND COALESCE(f."snapshot_type", 'entry') = 'entry'
                ORDER BY f."underlying" ASC, f."snapshot_time" ASC, f."option_symbol" ASC
                """,
                (target_filter,),
            )
            feature_rows = [dict(row) for row in cursor.fetchall()]
    for row in feature_rows:
        underlying = str(row.get("underlying") or "").upper()
        snapshot_time = _time_key(row.get("snapshot_time"))
        contract_ref = str(row.get("option_symbol") or "")
        payload = _coerce_json_mapping(row.get("feature_payload_json"))
        diagnostics = _coerce_json_mapping(row.get("feature_quality_diagnostics"))
        if not underlying or not snapshot_time or not contract_ref:
            continue
        option_right = payload.get("option_right") or payload.get("right") or payload.get("option_right_type")
        expiration = payload.get("expiration") or row.get("expiration")
        dte = payload.get("dte") or payload.get("days_to_expiration")
        mid = payload.get("mid_price") or payload.get("mid")
        implied_vol = payload.get("iv") or payload.get("implied_volatility") or payload.get("implied_vol")
        rows_by_key[(underlying, snapshot_time)].append(
            {
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
        )
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
            for output in _latest_succeeded_outputs(receipt):
                path = Path(str(output))
                if path.name != "equity_bar.csv":
                    continue
                for row in _read_bar_csv(path):
                    if replay_month and str(row["timestamp"])[:7] != replay_month:
                        continue
                    row["symbol"] = symbol
                    row["asset_class"] = "us_equity"
                    row["source_id"] = "alpaca_bars"
                    rows_by_target[symbol].append(row)
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
    for symbol_dir in sorted(path for path in equity_source_root.iterdir() if path.is_dir()):
        symbol = symbol_dir.name.upper()
        if symbol_filter and symbol not in symbol_filter:
            continue
        daily: dict[str, dict[str, Any]] = {}
        for csv_path in sorted(symbol_dir.glob("*/runs/*/saved/equity_bar.csv")):
            for row in _read_bar_csv(csv_path):
                timestamp = str(row["timestamp"])
                year_month = timestamp[:7]
                if year_month < "2021-01" or year_month > "2025-12":
                    continue
                date_text = str(row["date"])
                current = daily.get(date_text)
                if current is None:
                    daily[date_text] = {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timeframe": "1Day",
                        "timestamp": f"{date_text}T16:00:00-05:00",
                        "date": date_text,
                        "bar_open": float(row["bar_open"]),
                        "bar_high": float(row["bar_high"]),
                        "bar_low": float(row["bar_low"]),
                        "bar_close": float(row["bar_close"]),
                        "bar_volume": float(row["bar_volume"]),
                    }
                    continue
                current["bar_high"] = max(float(current["bar_high"]), float(row["bar_high"]))
                current["bar_low"] = min(float(current["bar_low"]), float(row["bar_low"]))
                current["bar_close"] = float(row["bar_close"])
                current["bar_volume"] = float(current["bar_volume"]) + float(row["bar_volume"])
        rows = sorted(daily.values(), key=lambda row: str(row["timestamp"]))
        if len(rows) >= 2:
            rows_by_target[symbol] = rows
    return rows_by_target


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
    if option_candidates:
        generators = _trading_model_generators()
        model_row = generators["model_09_option_expression"](
            [
                {
                    "available_time": timestamp,
                    "tradeable_time": timestamp,
                    "target_candidate_id": layer_outputs["target_candidate_id"],
                    "underlying_action_plan_ref": _as_mapping(layer_outputs["underlying_action_plan"]).get("model_ref"),
                    "underlying_action_plan": layer_outputs["underlying_action_plan"],
                    "layer_8_underlying_handoff": _as_mapping(layer_outputs["underlying_action_plan"]).get("handoff_to_layer_9") or {},
                    "market_context_state": layer_outputs["market_context_state"],
                    "event_context_vector": layer_outputs["event_failure_risk_vector"],
                    "option_expression_policy": {},
                    "option_contract_candidates": list(option_candidates),
                    "option_surface_status": "optionable_chain_available",
                    "option_chain_snapshot_ref": f"m09_option_expression_feature_generation:{target}:{_time_key(timestamp)}",
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
                "model_ref": f"{candidate_model_ref}/model_09_option_expression/{model_row['option_expression_plan_ref']}",
                "target_ref": target,
                "asset_expression_route": "listed_option_contract" if selected_contract else "option_expression_unfilled",
                "option_surface_status": model_row.get("option_surface_status") or "optionable_chain_available",
            }
        )
        return plan
    return {
        "model_ref": f"{candidate_model_ref}/model_09_option_expression/{target}/{timestamp}",
        "target_ref": target,
        "asset_expression_route": "direct_underlying_fallback",
        "option_surface_status": "optionable_chain_missing",
        "reason_codes": ["option_expression_source_missing_direct_underlying_replay_fallback"],
    }


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
    equity_target_dates: set[tuple[str, str]] = set()
    for target, rows in bars_by_target.items():
        for row in rows:
            if str(row.get("asset_class") or "") != "us_equity":
                continue
            date_text = str(row.get("date") or str(row.get("timestamp") or "")[:10])
            if date_text:
                equity_target_dates.add((target, date_text))
    selected_option_rows = [row for row in decision_rows if row.get("selected_option_contract_ref")]
    path_available_count = sum(1 for row in selected_option_rows if row.get("option_contract_path_status") == "available")
    path_missing_count = sum(1 for row in selected_option_rows if row.get("option_contract_path_status") == "missing")
    expected_snapshot_count = len(equity_target_dates)
    feature_snapshot_count = len(option_candidates_by_underlying_time)
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
        "expected_equity_target_date_snapshot_count": expected_snapshot_count,
        "feature_snapshot_coverage_ratio": feature_coverage_ratio,
        "contract_path_coverage_status": path_status,
        "contract_path_symbol_count": len(option_contract_paths_by_symbol),
        "contract_path_bar_count": sum(len(rows) for rows in option_contract_paths_by_symbol.values()),
        "selected_option_decision_count": len(selected_option_rows),
        "selected_option_path_available_count": path_available_count,
        "selected_option_path_missing_count": path_missing_count,
    }


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
    event_state = _event_failure_risk_state(candidate_model_ref=candidate_model_ref, available_time=available_time)
    quality_state = _quality_calibration_state()

    alpha_row = generators["model_05_alpha_confidence"](
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "market_context_state": market_state,
                "sector_context_state": sector_state,
                "target_context_state": target_state,
                "event_failure_risk_vector": event_state,
                "quality_calibration_state": quality_state,
            }
        ],
        after_cost_alpha_model=after_cost_alpha_model,
    )[0]
    alpha_vector = dict(alpha_row["alpha_confidence_vector"])
    alpha_score = _resolved_alpha_score(alpha_vector)
    alpha_vector.update(
        {
            "model_ref": f"{candidate_model_ref}/model_05_alpha_confidence/{alpha_row['alpha_confidence_vector_ref']}",
            "alpha_confidence_score": alpha_score,
            "score": alpha_score,
        }
    )

    policy_row = generators["model_06_dynamic_risk_policy"](
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "policy_scope": "target_candidate",
                "market_context_state": market_state,
                "systemic_event_risk_state": event_state,
                "alpha_confidence_vector": alpha_vector,
                "portfolio_exposure_state": _flat_portfolio_state(),
                "account_capacity_state": _account_capacity_state(),
            }
        ]
    )[0]
    risk_policy = dict(policy_row["dynamic_risk_policy_state"])
    selected_thresholds = _selected_entry_thresholds(entry_calibration)
    risk_policy.update(
        {
            "model_ref": f"{candidate_model_ref}/model_06_dynamic_risk_policy/{policy_row['dynamic_risk_policy_state_ref']}",
            "minimum_entry_alpha_confidence": selected_thresholds["minimum_entry_alpha_confidence"],
            "minimum_trade_intensity": selected_thresholds["minimum_trade_intensity"],
        }
    )
    policy_gate_state = _entry_policy_gate_state(entry_calibration)

    projection_row = generators["model_07_position_projection"](
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "alpha_confidence_vector": alpha_vector,
                "current_position_state": {"current_position_exposure_score": 0.0},
                "pending_position_state": {"pending_exposure_score": 0.0, "pending_order_fill_probability_estimate": 0.0},
                "position_level_friction": {"spread_cost_score": 0.05, "cost_to_adjust_position_score": 0.05},
                "price_location_state": {
                    "current_price": reference_price,
                    "reference_price": reference_price,
                    "alpha_reference_price": reference_price,
                    "thesis_intact_score": 1.0,
                },
                "portfolio_exposure_state": _flat_portfolio_state(),
                "risk_budget_state": {"risk_budget_fit_score": risk_policy.get("6_resolved_new_exposure_permission_score", 0.7)},
                "policy_gate_state": policy_gate_state,
            }
        ]
    )[0]
    projection_vector = dict(projection_row["position_projection_vector"])

    underlying_row = generators["model_08_underlying_action"](
        [
            {
                "available_time": available_time,
                "tradeable_time": available_time,
                "target_candidate_id": target_candidate_id,
                "alpha_confidence_vector": alpha_vector,
                "position_projection_vector": projection_vector,
                "current_underlying_position_state": {"current_underlying_exposure_score": 0.0},
                "pending_underlying_order_state": {"pending_underlying_exposure_score": 0.0, "pending_fill_probability_estimate": 0.0},
                "underlying_quote_state": {"reference_price": reference_price, "last_price": reference_price, "halt_status": "active"},
                "underlying_liquidity_state": {"spread_bps": 10.0, "dollar_volume": _dollar_volume(target_rows[index])},
                "risk_budget_state": {"risk_budget_fit_score": risk_policy.get("6_resolved_new_exposure_permission_score", 0.7)},
                "policy_gate_state": policy_gate_state,
            }
        ]
    )[0]
    underlying_plan = _execution_underlying_plan(
        plan=underlying_row["underlying_action_plan"],
        candidate_model_ref=candidate_model_ref,
        plan_ref=str(underlying_row["underlying_action_plan_ref"]),
        reference_price=reference_price,
    )
    target_state_for_execution = dict(target_state)
    target_state_for_execution.update({"current_price": reference_price, "last_price": reference_price, "mark_price": reference_price})
    return {
        "target_candidate_id": target_candidate_id,
        "available_time": available_time,
        "market_context_state": market_state,
        "target_context_state": target_state_for_execution,
        "event_failure_risk_vector": event_state,
        "alpha_confidence_vector": alpha_vector,
        "dynamic_risk_policy_state": risk_policy,
        "underlying_action_plan": underlying_plan,
        "prediction_score": alpha_score,
        "model_layer_refs": {
            "model_05_alpha_confidence": alpha_row["alpha_confidence_vector_ref"],
            "model_06_dynamic_risk_policy": policy_row["dynamic_risk_policy_state_ref"],
            "model_07_position_projection": projection_row["position_projection_vector_ref"],
            "model_08_underlying_action": underlying_row["underlying_action_plan_ref"],
        },
        "model_layer_diagnostics": _model_layer_diagnostics(
            alpha_vector=alpha_vector,
            risk_policy=risk_policy,
            projection_vector=projection_vector,
            underlying_plan=underlying_row["underlying_action_plan"],
            entry_calibration=entry_calibration,
        ),
    }


def _trading_model_generators() -> dict[str, Callable[[Iterable[Mapping[str, Any]]], list[dict[str, Any]]]]:
    try:
        from models.model_05_alpha_confidence.generator import generate_rows as generate_alpha_confidence
        from models.model_06_dynamic_risk_policy.generator import generate_rows as generate_dynamic_risk_policy
        from models.model_07_position_projection.generator import generate_rows as generate_position_projection
        from models.model_08_underlying_action.generator import generate_rows as generate_underlying_action
        from models.model_09_option_expression.generator import generate_rows as generate_option_expression
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "trading-model must be importable for model-group replay inference; "
            "include /root/projects/trading-model/src on PYTHONPATH"
        ) from exc
    return {
        "model_05_alpha_confidence": generate_alpha_confidence,
        "model_06_dynamic_risk_policy": generate_dynamic_risk_policy,
        "model_07_position_projection": generate_position_projection,
        "model_08_underlying_action": generate_underlying_action,
        "model_09_option_expression": generate_option_expression,
    }


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


def _entry_policy_gate_state(entry_calibration: Mapping[str, Any] | None) -> dict[str, Any]:
    selected = _selected_entry_thresholds(entry_calibration)
    return {
        "minimum_entry_alpha_confidence": selected["minimum_entry_alpha_confidence"],
        "minimum_trade_intensity": selected["minimum_trade_intensity"],
        "entry_threshold_calibration_status": str((entry_calibration or {}).get("calibration_status") or "uncalibrated_default"),
    }


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
    alpha_vector: Mapping[str, Any],
    risk_policy: Mapping[str, Any],
    projection_vector: Mapping[str, Any],
    underlying_plan: Mapping[str, Any],
    entry_calibration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dominant_horizon = str(underlying_plan.get("dominant_horizon") or projection_vector.get("7_dominant_projection_horizon") or "1D")
    dominant_suffix = dominant_horizon if dominant_horizon in {"1D", "1W"} else {"10min": "10min", "1h": "1h"}.get(dominant_horizon, "1D")
    diagnostics = _as_mapping(underlying_plan.get("diagnostics"))
    horizon_scores = _as_mapping(diagnostics.get("horizon_scores"))
    dominant_scores = _as_mapping(horizon_scores.get(dominant_horizon))
    return {
        "entry_thresholds": _selected_entry_thresholds(entry_calibration),
        "model_05_alpha_confidence": {
            "alpha_confidence_score": _safe_float(alpha_vector.get(f"5_alpha_confidence_score_{dominant_suffix}")),
            "expected_return_score": _safe_float(alpha_vector.get(f"5_expected_return_score_{dominant_suffix}")),
            "alpha_direction_score": _safe_float(alpha_vector.get(f"5_alpha_direction_score_{dominant_suffix}")),
            "path_quality_score": _safe_float(alpha_vector.get(f"5_path_quality_score_{dominant_suffix}")),
            "reversal_risk_score": _safe_float(alpha_vector.get(f"5_reversal_risk_score_{dominant_suffix}")),
            "drawdown_risk_score": _safe_float(alpha_vector.get(f"5_drawdown_risk_score_{dominant_suffix}")),
        },
        "model_06_dynamic_risk_policy": {
            "minimum_entry_alpha_confidence": _safe_float(risk_policy.get("minimum_entry_alpha_confidence")),
            "minimum_trade_intensity": _safe_float(risk_policy.get("minimum_trade_intensity")),
            "new_exposure_permission_score": _safe_float(risk_policy.get("6_resolved_new_exposure_permission_score")),
        },
        "model_07_position_projection": {
            "dominant_projection_horizon": projection_vector.get("7_dominant_projection_horizon"),
            "target_exposure_score": _safe_float(projection_vector.get(f"7_target_exposure_score_{dominant_suffix}")),
            "position_gap_score": _safe_float(projection_vector.get(f"7_position_gap_score_{dominant_suffix}")),
            "expected_position_utility_score": _safe_float(projection_vector.get(f"7_expected_position_utility_score_{dominant_suffix}")),
            "projection_confidence_score": _safe_float(projection_vector.get(f"7_projection_confidence_score_{dominant_suffix}")),
            "risk_budget_fit_score": _safe_float(projection_vector.get(f"7_risk_budget_fit_score_{dominant_suffix}")),
            "cost_to_adjust_position_score": _safe_float(projection_vector.get(f"7_cost_to_adjust_position_score_{dominant_suffix}")),
        },
        "model_08_underlying_action": {
            "resolved_underlying_action_type": underlying_plan.get("planned_underlying_action_type"),
            "resolved_action_side": underlying_plan.get("action_side"),
            "dominant_horizon": dominant_horizon,
            "reason_codes": underlying_plan.get("reason_codes") or [],
            "hard_gate_reason_codes": diagnostics.get("hard_gate_reason_codes") or [],
            "soft_gate_reason_codes": dominant_scores.get("soft_gate_reason_codes") or [],
            "dominant_horizon_scores": {
                "trade_eligibility_score": _safe_float(dominant_scores.get("trade_eligibility_score")) or 0.0,
                "trade_intensity_score": _safe_float(dominant_scores.get("trade_intensity_score")) or 0.0,
                "entry_quality_score": _safe_float(dominant_scores.get("entry_quality_score")) or 0.0,
                "action_confidence_score": _safe_float(dominant_scores.get("action_confidence_score")) or 0.0,
                "action_direction_score": _safe_float(dominant_scores.get("action_direction_score")) or 0.0,
                "expected_return_score": _safe_float(dominant_scores.get("expected_return_score")) or 0.0,
                "reward_risk_score": _safe_float(dominant_scores.get("reward_risk_score")) or 0.0,
                "adverse_risk_score": _safe_float(dominant_scores.get("adverse_risk_score")) or 0.0,
                "minimum_entry_alpha_confidence": _safe_float(dominant_scores.get("minimum_entry_alpha_confidence")),
                "minimum_trade_intensity": _safe_float(dominant_scores.get("minimum_trade_intensity")),
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


def _event_failure_risk_state(*, candidate_model_ref: str, available_time: str) -> dict[str, Any]:
    state = {"model_ref": f"{candidate_model_ref}/model_04_event_failure_risk/{available_time}"}
    for suffix in ("10min", "1h", "1D", "1W"):
        state.update(
            {
                f"4_event_applicability_confidence_score_{suffix}": 0.0,
                f"4_event_strategy_failure_risk_score_{suffix}": 0.0,
                f"4_event_entry_block_pressure_score_{suffix}": 0.0,
                f"4_event_evidence_quality_score_{suffix}": 0.75,
                f"4_event_strategy_disable_pressure_score_{suffix}": 0.0,
                f"4_event_path_risk_amplifier_score_{suffix}": 0.0,
                f"4_event_session_gap_risk_score_{suffix}": 0.0,
                f"4_event_exposure_cap_pressure_score_{suffix}": 0.0,
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


def _execution_underlying_plan(
    *,
    plan: Mapping[str, Any],
    candidate_model_ref: str,
    plan_ref: str,
    reference_price: float,
) -> dict[str, Any]:
    entry = _as_mapping(plan.get("entry_plan"))
    path = _as_mapping(plan.get("price_path_expectation"))
    risk = _as_mapping(plan.get("risk_plan"))
    action_side = str(plan.get("action_side") or "").strip()
    entry_price = _safe_float(entry.get("expected_entry_price")) or reference_price
    worst_price = _safe_float(entry.get("worst_acceptable_entry_price")) or entry_price
    target_low = _safe_float(path.get("target_price_low"))
    target_high = _safe_float(path.get("target_price_high"))
    target_price = _safe_float(path.get("expected_target_price")) or _safe_float(risk.get("take_profit_price"))
    stop_price = _safe_float(risk.get("stop_loss_price"))
    invalidation_price = _safe_float(risk.get("thesis_invalidation_price")) or stop_price
    output = dict(plan)
    output.update(
        {
            "model_ref": f"{candidate_model_ref}/model_08_underlying_action/{plan_ref}",
            "entry_direction": "long" if action_side == "long" else "short" if action_side == "short" else None,
            "entry_zone": {
                "low": min(entry_price, worst_price, reference_price),
                "high": max(entry_price, worst_price, reference_price),
            },
            "target_price": target_price,
            "take_profit_zone": {"low": min(target_low, target_high), "high": max(target_low, target_high)}
            if target_low is not None and target_high is not None
            else None,
            "model_invalidation_price": invalidation_price,
            "hard_stop_price": stop_price,
            "expected_horizon": plan.get("dominant_horizon"),
            "current_price": reference_price,
            "reference_price": reference_price,
        }
    )
    return output


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


def _trade_risk_cap(reference_price: float) -> dict[str, Any]:
    return {
        "max_loss_usd": max(10.0, reference_price * 0.05),
        "max_loss_pct": 0.02,
        "time_stop_at": "2026-01-01T00:00:00Z",
        "cap_enforcement_mode": "broker_native_stop",
        "cap_failure_action": "reject_order",
        "model_invalidation_price": reference_price * 0.97,
        "hard_stop_price": reference_price * 0.96,
        "planned_quantity": 1.0,
        "planned_limit_price": reference_price,
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
    if not _string_set(manifest.get("tradable_target_refs")):
        errors.append("dataset manifest tradable_target_refs must include at least one live-equivalent replay target")
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
    "REPLAY_DECISION_ROW_CONTRACT",
    "REPLAY_EXECUTION_RUN_CONTRACT",
    "ReplayExecutionResult",
    "build_candidate_policy_replay_execution_run",
    "build_crypto_replay_execution_run",
]
