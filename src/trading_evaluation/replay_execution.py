"""Side-effect-free Replay execution over frozen source artifacts.

This module orchestrates replay decisions through `trading-execution`. It reads
already-frozen local source artifacts and emits evaluation decision rows. It
does not call providers, train models, activate models, call brokers, or mutate
accounts.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .execution_runtime import EXECUTION_REPLAY_ROUTE_REF, build_replay_runtime_dry_run

REPLAY_EXECUTION_RUN_CONTRACT = "evaluation_replay_execution_run"
REPLAY_DECISION_ROW_CONTRACT = "evaluation_replay_decision_row"
REPLAY_PROGRESS_CONTRACT = "evaluation_replay_progress"
CRYPTO_SPOT_ACCOUNT_SLEEVE = "crypto_spot_account"
CRYPTO_SYMBOLS_BY_INSTRUMENT = {
    "BTC-USDT": "BTC",
    "ETH-USDT": "ETH",
    "SOL-USDT": "SOL",
}
DEFAULT_DATASET_ROOT = Path("/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy")


@dataclass(frozen=True)
class ReplayExecutionResult:
    """Replay execution receipt and decision-row output paths."""

    receipt_path: Path
    decision_rows_path: Path
    progress_path: Path
    receipt: dict[str, Any]


def build_crypto_replay_execution_run(
    *,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    output_dir: Path | None = None,
    run_id: str | None = None,
    candidate_model_ref: str = "trading-model://candidate_policy_replay/current_deterministic_crypto_policy",
    replay_contract_ref: str = "trading-evaluation/replays/promotion_replay_candidate_policy.json",
    max_decision_rows: int | None = None,
    generated_at_utc: str | None = None,
    progress_path: Path | None = None,
) -> ReplayExecutionResult:
    """Run the frozen crypto sleeve through the execution-owned Replay route."""

    manifest = _load_json(dataset_root / "dataset_manifest.json")
    freeze_receipt = _load_json(dataset_root / "replay_freeze_receipt.json")
    _validate_frozen_dataset(manifest, freeze_receipt)
    generated_at = generated_at_utc or _now_utc()
    run_id = run_id or f"crypto_spot_replay_{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    output_dir = output_dir or dataset_root / "replay_execution_runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_rows_path = output_dir / "decision_rows.jsonl"
    receipt_path = output_dir / "replay_execution_receipt.json"
    progress_path = progress_path or dataset_root / "replay_progress.jsonl"

    bars_by_target = _load_crypto_bars(Path(str(manifest["feed_acquisition_plan_ref"])))
    market_dates = sorted({row["date"] for rows in bars_by_target.values() for row in rows})
    decision_rows = _build_crypto_decision_rows(
        bars_by_target=bars_by_target,
        market_dates=market_dates,
        run_id=run_id,
        candidate_model_ref=candidate_model_ref,
        replay_contract_ref=replay_contract_ref,
        max_decision_rows=max_decision_rows,
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
        "execution_scope": "crypto_spot_account_fixed_candidate_pool",
        "candidate_model_ref": candidate_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "replay_route_ref": EXECUTION_REPLAY_ROUTE_REF,
        "dataset_root": str(dataset_root),
        "dataset_manifest_ref": str(dataset_root / "dataset_manifest.json"),
        "replay_freeze_receipt_ref": str(dataset_root / "replay_freeze_receipt.json"),
        "decision_rows_ref": str(decision_rows_path),
        "progress_ref": str(progress_path),
        "decision_row_count": len(decision_rows),
        "completed_replay_month_count": len(progress_rows),
        "target_refs": sorted(bars_by_target),
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
            "crypto sleeve replay over frozen OKX daily bars",
            "equity/options Alpaca rows remain candidate-dependent and deferred until point-in-time candidate materialization",
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
                "execution_scope": "crypto_spot_account_fixed_candidate_pool",
                "decision_row_count": len(month_rows),
                "target_refs": sorted({str(row.get("target_ref") or "") for row in month_rows if row.get("target_ref")}),
                "receipt_ref": str(receipt_path),
                "decision_rows_ref": str(decision_rows_path),
                "generated_at_utc": generated_at_utc,
            }
        )
    return progress_rows


def _build_crypto_decision_rows(
    *,
    bars_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    market_dates: Sequence[str],
    run_id: str,
    candidate_model_ref: str,
    replay_contract_ref: str,
    max_decision_rows: int | None,
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
            alpha_score = _alpha_score(target_rows, index)
            reference_price = float(bar["bar_close"])
            replay_result = build_replay_runtime_dry_run(
                account_sleeve_id=CRYPTO_SPOT_ACCOUNT_SLEEVE,
                target_ref=target,
                market_universe=market_universe,
                alpha_confidence_vector={
                    "model_ref": candidate_model_ref,
                    "alpha_confidence_score": alpha_score,
                },
                dynamic_risk_policy_state={
                    "model_ref": f"{candidate_model_ref}/dynamic_risk_policy",
                    "minimum_entry_alpha_confidence": 0.55,
                },
                trade_risk_cap=_trade_risk_cap(reference_price),
                market_snapshot={
                    "market_snapshot_ref": f"storage://replay/okx/{target}/{date_text}",
                    "reference_price": reference_price,
                    "close_price": reference_price,
                },
                replay_fill_policy={
                    "replay_fill_policy_ref": "replay_fill_policy://crypto_spot_daily_close/slippage_10_fee_5_bps",
                    "slippage_bps": 10,
                    "fee_bps": 5,
                },
                generated_at_utc=str(bar["timestamp"]),
            )
            entry = replay_result["decision_records"]["entry_decision"]
            order_intent = replay_result["decision_records"]["execution_order_intent"]
            fill = replay_result["decision_records"]["simulated_fill_event"]
            gross_return = (float(next_bar["bar_close"]) - reference_price) / reference_price
            filled = fill.get("fill_status") == "simulated_filled"
            cost = 0.0015 if filled else 0.0
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
                    "account_sleeve_id": CRYPTO_SPOT_ACCOUNT_SLEEVE,
                    "target_ref": target,
                    "instrument_ref": entry["instrument_ref"],
                    "timestamp": bar["timestamp"],
                    "next_timestamp": next_bar["timestamp"],
                    "decision_status": entry["decision_status"],
                    "decision_action": entry["decision_action"],
                    "action": entry["decision_action"],
                    "fill_status": fill["fill_status"],
                    "prediction_score": alpha_score,
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
                "asset_class": "crypto_spot",
                "reference_price": bar["bar_close"],
            }
        )
    return rows


def _load_crypto_bars(plan_path: Path) -> dict[str, list[dict[str, Any]]]:
    rows_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with plan_path.open(newline="", encoding="utf-8") as handle:
        for plan_row in csv.DictReader(handle):
            if plan_row.get("source_id") != "okx_crypto_market_data" or plan_row.get("coverage_status") != "available":
                continue
            receipt = _load_json(Path(str(plan_row["coverage_receipt_path"])))
            for output in _latest_succeeded_outputs(receipt):
                path = Path(str(output))
                if path.name != "crypto_bar.csv":
                    continue
                for bar in _read_bar_csv(path):
                    target = CRYPTO_SYMBOLS_BY_INSTRUMENT.get(str(bar["symbol"]).upper())
                    if target:
                        rows_by_target[target].append(bar)
    deduped: dict[str, list[dict[str, Any]]] = {}
    for target, rows in rows_by_target.items():
        by_timestamp = {str(row["timestamp"]): row for row in rows}
        deduped[target] = sorted(by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    return deduped


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


def _alpha_score(rows: Sequence[Mapping[str, Any]], index: int) -> float:
    momentum_7d = _window_return(rows, index, 7)
    momentum_30d = _window_return(rows, index, 30)
    daily = _daily_return(rows, index)
    score = 0.52 + momentum_7d * 2.0 + momentum_30d * 0.5 + daily
    return max(0.05, min(0.95, score))


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
    "build_crypto_replay_execution_run",
]
