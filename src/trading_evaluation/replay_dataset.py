"""Replay dataset preparation and freeze manifests.

This module turns an accepted candidate-policy replay contract into
concrete storage-side preparation artifacts. It does not call providers, mutate
SQL, select option contracts, or write active model state.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable as IterableABC
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .replay import ReplayContract, validate_replay_contract

REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT = "replay_dataset_preparation_manifest"
REPLAY_WINDOW_MANIFEST_CONTRACT = "replay_window_manifest"
REPLAY_FEED_ACQUISITION_PLAN_CONTRACT = "replay_feed_acquisition_plan"
REPLAY_COVERAGE_SUMMARY_CONTRACT = "replay_coverage_summary"
REPLAY_DATASET_FREEZE_RECEIPT_CONTRACT = "replay_dataset_freeze_receipt"
DEFAULT_OUTPUT_ROOT = Path("/root/projects/trading-storage/storage/05_replay_datasets")
DEFAULT_DATA_ROOT = Path("/root/projects/trading-storage/storage/01_source_data")
DEFAULT_SOURCE_CONTRACT_REF = "trading-evaluation/replays/promotion_replay_candidate_policy.json"
CRYPTO_SPOT_INSTRUMENT_BY_TARGET = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "SOL": "SOL-USDT",
}
ACCEPTED_DEFERRED_SOURCE_IDS = frozenset({"alpaca_bars", "alpaca_liquidity", "alpaca_news"})

REPLAY_WINDOW_FIELDS = [
    "contract_id",
    "replay_mode",
    "start_date",
    "end_date",
    "min_trading_days",
    "candidate_policy_ref",
    "replay_route_ref",
    "market_condition_tags",
    "selection_metric_refs",
]

ACQUISITION_FIELDS = [
    "acquisition_id",
    "contract_id",
    "source_id",
    "feed",
    "target_ref",
    "asset_class",
    "instrument_type",
    "month",
    "start_date",
    "end_date_exclusive",
    "timeframe",
    "acquisition_mode",
    "output_root",
    "expected_output_ref",
    "coverage_status",
    "coverage_receipt_path",
    "params_json",
    "notes",
]

COVERAGE_FIELDS = [
    "contract_id",
    "source_id",
    "required_acquisition_count",
    "available_acquisition_count",
    "deferred_acquisition_count",
    "missing_acquisition_count",
    "coverage_status",
    "notes",
]


@dataclass(frozen=True)
class PreparedReplayDataset:
    """Paths and summary for a prepared replay dataset manifest."""

    manifest_path: Path
    replay_window_manifest_path: Path
    feed_acquisition_plan_path: Path
    coverage_summary_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class FrozenReplayDataset:
    """Paths and receipt for a frozen replay dataset contract."""

    manifest_path: Path
    freeze_receipt_path: Path
    freeze_receipt: dict[str, Any]


def prepare_replay_dataset(
    payload: Mapping[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    data_root: Path = DEFAULT_DATA_ROOT,
    source_contract_ref: str = DEFAULT_SOURCE_CONTRACT_REF,
    prepared_at_utc: str | None = None,
) -> PreparedReplayDataset:
    """Write a replay dataset preparation bundle."""

    validation = validate_replay_contract(payload)
    if validation.validation_status != "passed" or validation.contract is None:
        raise ValueError("replay contract validation failed: " + "; ".join(validation.errors))

    contract = validation.contract
    pre_replay_target_refs = _load_tradable_universe_refs(Path(contract.tradable_universe_ref))
    if not pre_replay_target_refs:
        raise ValueError("replay dataset preparation requires non-empty tradable_universe_ref")
    prepared_at = prepared_at_utc or _now_utc()
    dataset_root = output_root / contract.contract_id
    dataset_root.mkdir(parents=True, exist_ok=True)

    replay_window_rows = _replay_window_rows(contract)
    acquisition_rows = _acquisition_rows(contract, data_root=data_root, tradable_target_refs=pre_replay_target_refs)
    coverage_rows = _coverage_rows(contract, acquisition_rows)

    replay_window_manifest_path = dataset_root / "replay_window_manifest.csv"
    feed_acquisition_plan_path = dataset_root / "feed_acquisition_plan.csv"
    coverage_summary_path = dataset_root / "coverage_summary.csv"
    manifest_path = dataset_root / "dataset_manifest.json"

    _write_csv(replay_window_manifest_path, REPLAY_WINDOW_FIELDS, replay_window_rows)
    _write_csv(feed_acquisition_plan_path, ACQUISITION_FIELDS, acquisition_rows)
    _write_csv(coverage_summary_path, COVERAGE_FIELDS, coverage_rows)

    manifest = {
        "contract_type": REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT,
        "contract_id": contract.contract_id,
        "replay_mode": contract.replay_mode,
        "preparation_status": "prepared_candidate_policy_replay_acquisition_bundle",
        "freeze_status": "not_frozen",
        "prepared_at_utc": prepared_at,
        "source_contract_ref": source_contract_ref,
        "candidate_policy_ref": contract.candidate_policy_ref,
        "replay_route_ref": contract.replay_route_ref,
        "candidate_fold_id": contract.candidate_fold_id,
        "fold_id": contract.candidate_fold_id,
        "tradable_universe_policy_ref": contract.tradable_universe_policy_ref,
        "tradable_universe_ref": contract.tradable_universe_ref,
        "pre_replay_target_refs": list(pre_replay_target_refs),
        "tradable_target_refs": list(pre_replay_target_refs),
        "candidate_discovery_policy": {
            "mode": "on_demand_from_replay_layer_outputs",
            "pre_replay_scope": "layer_01_02_base_market_context_only",
            "equity_and_option_targets": "not_preexpanded",
            "downstream_acquisition": "layer_02_sector_signal_then_target_and_option_chain_lookup",
        },
        "dataset_root": str(dataset_root),
        "storage_ref": f"storage://trading-storage/05_replay_datasets/{contract.contract_id}/",
        "replay_window_count": len(replay_window_rows),
        "feed_acquisition_count": len(acquisition_rows),
        "available_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "available"),
        "deferred_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "deferred"),
        "missing_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "missing"),
        "replay_window_manifest_ref": str(replay_window_manifest_path),
        "feed_acquisition_plan_ref": str(feed_acquisition_plan_path),
        "coverage_summary_ref": str(coverage_summary_path),
        "artifact_refs": [str(replay_window_manifest_path), str(feed_acquisition_plan_path), str(coverage_summary_path)],
        "safety": {
            "provider_calls_performed": False,
            "sql_mutation_performed": False,
            "replay_freeze_performed": False,
            "model_training_performed": False,
            "model_activation_performed": False,
            "broker_execution_performed": False,
            "account_mutation_performed": False,
            "manager_request_route_used": False,
            "acquisition_requests_allow_live_provider_calls": False,
        },
        "known_deferred_requirements": [
            "one_shot_provider_acquisition_requires_separate_gate",
            "replay_dataset_requires_layer_01_02_base_market_context_scope",
            "replay_execution_expands_equity_and_option_targets_on_demand_from_layer_outputs",
            "thetadata_option_selection_snapshot_expands_from_model_buy_point_decisions",
            "thetadata_option_primary_tracking_and_event_timeline_expand_after_snapshot_contract_selection",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return PreparedReplayDataset(
        manifest_path=manifest_path,
        replay_window_manifest_path=replay_window_manifest_path,
        feed_acquisition_plan_path=feed_acquisition_plan_path,
        coverage_summary_path=coverage_summary_path,
        manifest=manifest,
    )


def freeze_replay_dataset(
    dataset_root: Path,
    *,
    frozen_at_utc: str | None = None,
    freeze_reason: str = "accepted_candidate_policy_replay_source_coverage",
) -> FrozenReplayDataset:
    """Freeze a prepared replay dataset after local coverage validation.

    The freeze is a storage-side contract mutation only. It validates the
    prepared manifest and coverage summary, writes a freeze receipt, and marks
    the dataset manifest as frozen. It never calls providers, mutates SQL,
    trains or activates models, or touches broker/account state.
    """

    manifest_path = dataset_root / "dataset_manifest.json"
    coverage_summary_path = dataset_root / "coverage_summary.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"dataset manifest not found: {manifest_path}")
    if not coverage_summary_path.exists():
        raise FileNotFoundError(f"coverage summary not found: {coverage_summary_path}")

    manifest = _load_json_object(manifest_path)
    coverage_rows = _read_coverage_summary(coverage_summary_path)
    errors = _freeze_validation_errors(manifest, coverage_rows)
    if errors:
        raise ValueError("replay dataset freeze validation failed: " + "; ".join(errors))

    frozen_at = frozen_at_utc or _now_utc()
    freeze_receipt_path = dataset_root / "replay_freeze_receipt.json"
    complete_sources = sorted(row["source_id"] for row in coverage_rows if row["coverage_status"] == "complete")
    deferred_sources = sorted(row["source_id"] for row in coverage_rows if row["coverage_status"] == "deferred")
    freeze_receipt = {
        "contract_type": REPLAY_DATASET_FREEZE_RECEIPT_CONTRACT,
        "contract_id": manifest["contract_id"],
        "freeze_status": "frozen",
        "freeze_reason": freeze_reason,
        "frozen_at_utc": frozen_at,
        "dataset_root": str(dataset_root),
        "dataset_manifest_ref": str(manifest_path),
        "coverage_summary_ref": str(coverage_summary_path),
        "complete_source_ids": complete_sources,
        "accepted_deferred_source_ids": deferred_sources,
        "known_deferred_requirements": manifest.get("known_deferred_requirements", []),
        "validation": {
            "validation_status": "passed",
            "missing_feed_acquisition_count": int(manifest.get("missing_feed_acquisition_count", 0)),
            "deferred_feed_acquisition_count": int(manifest.get("deferred_feed_acquisition_count", 0)),
            "accepted_deferred_policy": "replay_execution_materializes_candidate_target_data_on_demand_after_layer_outputs",
        },
        "safety": {
            "provider_calls_performed": False,
            "sql_mutation_performed": False,
            "replay_freeze_performed": True,
            "model_training_performed": False,
            "model_activation_performed": False,
            "broker_execution_performed": False,
            "account_mutation_performed": False,
            "manager_request_route_used": False,
        },
    }

    updated_manifest = dict(manifest)
    updated_manifest.update(
        {
            "freeze_status": "frozen",
            "frozen_at_utc": frozen_at,
            "freeze_reason": freeze_reason,
            "replay_freeze_receipt_ref": str(freeze_receipt_path),
        }
    )
    updated_safety = dict(updated_manifest.get("safety") or {})
    updated_safety["replay_freeze_performed"] = True
    updated_manifest["safety"] = updated_safety
    artifact_refs = list(updated_manifest.get("artifact_refs") or [])
    if str(freeze_receipt_path) not in artifact_refs:
        artifact_refs.append(str(freeze_receipt_path))
    updated_manifest["artifact_refs"] = artifact_refs

    freeze_receipt_path.write_text(json.dumps(freeze_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(updated_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return FrozenReplayDataset(
        manifest_path=manifest_path,
        freeze_receipt_path=freeze_receipt_path,
        freeze_receipt=freeze_receipt,
    )


def _replay_window_rows(contract: ReplayContract) -> list[dict[str, Any]]:
    return [
        {
            "contract_id": contract.contract_id,
            "replay_mode": contract.replay_mode,
            "start_date": contract.start_date.isoformat(),
            "end_date": contract.end_date.isoformat(),
            "min_trading_days": contract.min_trading_days,
            "candidate_policy_ref": contract.candidate_policy_ref,
            "replay_route_ref": contract.replay_route_ref,
            "market_condition_tags": _join(contract.market_condition_tags),
            "selection_metric_refs": _join(contract.selection_metric_refs),
        }
    ]


def _acquisition_rows(
    contract: ReplayContract,
    *,
    data_root: Path,
    tradable_target_refs: Iterable[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in _replay_sources():
        for window in _replay_months(contract):
            rows.extend(
                _acquisition_rows_for_source_window(
                    contract,
                    source,
                    window,
                    data_root=data_root,
                    tradable_target_refs=tradable_target_refs,
                )
            )
    return rows


def _acquisition_rows_for_source_window(
    contract: ReplayContract,
    source: Mapping[str, str],
    window: Mapping[str, str],
    *,
    data_root: Path,
    tradable_target_refs: Iterable[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    month = window["month"]
    if source["source_id"] == "okx_crypto_market_data":
        target_refs = _crypto_target_refs(tradable_target_refs)
        for target_ref in target_refs:
            instrument_ref = CRYPTO_SPOT_INSTRUMENT_BY_TARGET[target_ref]
            instrument_token = instrument_ref.lower().replace("-", "_")
            rows.append(
                _acquisition_row(
                    contract,
                    source,
                    window,
                    data_root=data_root,
                    acquisition_suffix=f"{instrument_token}/{month}",
                    target_ref=target_ref,
                    asset_class="crypto_spot",
                    instrument_type="spot",
                    params_extra={"instId": instrument_ref, "target_ref": target_ref, "target_refs": [target_ref]},
                    notes_suffix=f"; crypto spot instrument {instrument_ref}",
                )
            )
        return rows
    if source.get("candidate_dependent") == "on_demand":
        return rows
    if source.get("candidate_dependent") == "base_target_refs":
        for target_ref in _equity_target_refs(tradable_target_refs):
            rows.append(
                _acquisition_row(
                    contract,
                    source,
                    window,
                    data_root=data_root,
                    acquisition_suffix=f"{target_ref.lower()}/{month}",
                    target_ref=target_ref,
                    asset_class="us_equity",
                    instrument_type="underlying_or_listed_option",
                    params_extra={
                        "symbol": target_ref,
                        "symbols": [target_ref],
                        "target_ref": target_ref,
                        "target_refs": [target_ref],
                        "underlying_symbol": target_ref,
                        "instrument_route": "live_equivalent_underlying_then_option_expression",
                    },
                    notes_suffix=f"; Layer 1/2 base market-context target {target_ref}",
                )
            )
        return rows
    rows.append(
        _acquisition_row(
            contract,
            source,
            window,
            data_root=data_root,
            acquisition_suffix=month,
            params_extra={"target_refs": list(tradable_target_refs)},
        )
    )
    return rows


def _acquisition_row(
    contract: ReplayContract,
    source: Mapping[str, str],
    window: Mapping[str, str],
    *,
    data_root: Path,
    acquisition_suffix: str | None = None,
    coverage_status_override: str | None = None,
    target_ref: str = "",
    asset_class: str = "",
    instrument_type: str = "",
    params_extra: Mapping[str, Any] | None = None,
    notes_suffix: str = "",
) -> dict[str, str]:
    month = window["month"]
    suffix = acquisition_suffix or month
    acquisition_id = _acquisition_id(contract.contract_id, source["source_id"], suffix)
    source_output_root = _coverage_output_root(data_root, source["source_id"], contract.contract_id, suffix)
    receipt_path = _coverage_receipt_path(
        data_root=data_root,
        source_id=source["source_id"],
        contract_id=contract.contract_id,
        suffix=suffix,
        source_output_root=source_output_root,
    )
    params = _feed_params(contract, source, window)
    params.update(dict(params_extra or {}))
    coverage_status = coverage_status_override or ("available" if _receipt_succeeded(receipt_path) else "missing")
    return {
        "acquisition_id": acquisition_id,
        "contract_id": contract.contract_id,
        "source_id": source["source_id"],
        "feed": source["feed"],
        "target_ref": target_ref,
        "asset_class": asset_class,
        "instrument_type": instrument_type,
        "month": month,
        "start_date": window["start_date"],
        "end_date_exclusive": window["end_date_exclusive"],
        "timeframe": source["timeframe"],
        "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
        "output_root": str(source_output_root),
        "expected_output_ref": _expected_output_ref(source["source_id"], contract.contract_id, suffix),
        "coverage_status": coverage_status,
        "coverage_receipt_path": str(receipt_path),
        "params_json": json.dumps(params, sort_keys=True),
        "notes": source["notes"] + notes_suffix,
    }


def _replay_sources() -> tuple[dict[str, str], ...]:
    return (
        {
            "source_id": "alpaca_bars",
            "feed": "01_feed_alpaca_bars",
            "timeframe": "1Day",
            "notes": "Layer 1/2 base market-context daily OHLCV surface reused from canonical monthly backfill",
            "candidate_dependent": "base_target_refs",
        },
        {
            "source_id": "alpaca_liquidity",
            "feed": "02_feed_alpaca_liquidity",
            "timeframe": "1Min",
            "notes": "on-demand replay liquidity and spread surface for candidates admitted by replay layer outputs",
            "candidate_dependent": "on_demand",
        },
        {
            "source_id": "alpaca_news",
            "feed": "03_feed_alpaca_news",
            "timeframe": "event_time",
            "notes": "on-demand replay symbol-scoped news evidence after point-in-time candidate admission",
            "candidate_dependent": "on_demand",
        },
        {
            "source_id": "gdelt_news",
            "feed": "05_feed_gdelt_news",
            "timeframe": "event_time",
            "notes": "broad market, sector, theme, and candidate news evidence for replay",
        },
        {
            "source_id": "trading_economics_calendar_web",
            "feed": "07_feed_trading_economics_calendar_web",
            "timeframe": "event_time",
            "notes": "high-importance U.S. macro calendar event evidence for replay",
        },
        {
            "source_id": "okx_crypto_market_data",
            "feed": "04_feed_okx_crypto_market_data",
            "timeframe": "1Day",
            "notes": "candidate-policy replay crypto daily market data surface",
        },
    )


def _feed_params(contract: ReplayContract, source: Mapping[str, str], window: Mapping[str, str]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "contract_id": contract.contract_id,
        "candidate_fold_id": contract.candidate_fold_id,
        "candidate_policy_ref": contract.candidate_policy_ref,
        "replay_route_ref": contract.replay_route_ref,
        "start": window["start_date"],
        "end": window["end_date_exclusive"],
        "timeframe": source["timeframe"],
        "replay_acquisition_policy": "candidate_policy_replay_monthly_surface",
        "replay_cache_policy": "monthly_ephemeral_cache",
        "post_replay_retention_policy": "retain_receipts_and_delete_replay_cache_after_month_operation",
        "source_id": source["source_id"],
    }
    if source["source_id"] == "gdelt_news":
        params.update({"start_date": window["start_date"], "end_date": window["end_date_exclusive"], "max_rows": 100})
    if source["source_id"] == "trading_economics_calendar_web":
        params.update(
            {
                "start_date": window["start_date"],
                "end_date": window["end_date_exclusive"],
                "allow_live_fetch": True,
                "date_range_mode": "custom",
                "use_authenticated_cookies": False,
                "country": "United States",
                "importance": "3",
                "max_window_days": 45,
                "persist_failure_diagnostics": True,
            }
        )
    if source["source_id"] in {"alpaca_bars", "alpaca_liquidity"}:
        params.update({"limit": 1000, "max_pages": 10})
    if source["source_id"] == "alpaca_news":
        params.update({"limit": 50, "max_pages": 10})
    if source["source_id"] == "okx_crypto_market_data":
        params.update({"limit": 100, "max_pages": 1})
    return params


def _equity_target_refs(target_refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(target for target in _target_refs(target_refs) if target not in CRYPTO_SPOT_INSTRUMENT_BY_TARGET)


def _crypto_target_refs(target_refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(target for target in _target_refs(target_refs) if target in CRYPTO_SPOT_INSTRUMENT_BY_TARGET)


def _target_refs(target_refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(target).strip().upper() for target in target_refs if str(target).strip()}))


def _load_tradable_universe_refs(path: Path) -> tuple[str, ...]:
    if not path.exists():
        raise FileNotFoundError(f"tradable universe artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return _target_refs(str(item) for item in payload)
    if not isinstance(payload, Mapping):
        raise ValueError(f"tradable universe artifact must be an object or list: {path}")
    raw = (
        payload.get("pre_replay_target_refs")
        or payload.get("base_target_refs")
        or payload.get("tradable_target_refs")
        or payload.get("tradable_symbols")
        or payload.get("symbols")
        or []
    )
    if isinstance(raw, str):
        return _target_refs(item for item in raw.split(","))
    if isinstance(raw, IterableABC):
        return _target_refs(str(item) for item in raw)
    return ()


def _replay_months(contract: ReplayContract) -> list[dict[str, str]]:
    current = date(contract.start_date.year, contract.start_date.month, 1)
    end_month = date(contract.end_date.year, contract.end_date.month, 1)
    windows: list[dict[str, str]] = []
    while current <= end_month:
        next_month = _next_month(current)
        start = max(contract.start_date, current)
        end = min(contract.end_date, next_month)
        if end > start:
            windows.append(
                {
                    "month": f"{current.year:04d}-{current.month:02d}",
                    "start_date": start.isoformat(),
                    "end_date_exclusive": end.isoformat(),
                }
            )
        current = next_month
    return windows


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _coverage_rows(contract: ReplayContract, acquisition_rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in acquisition_rows:
        grouped.setdefault(row["source_id"], []).append(row)
    rows: list[dict[str, Any]] = []
    for source_id in sorted(grouped):
        source_rows = grouped[source_id]
        available = sum(1 for row in source_rows if row["coverage_status"] == "available")
        deferred = sum(1 for row in source_rows if row["coverage_status"] == "deferred")
        missing = sum(1 for row in source_rows if row["coverage_status"] == "missing")
        required = len(source_rows)
        if available == required:
            coverage_status = "complete"
        elif available + deferred == required:
            coverage_status = "deferred"
        else:
            coverage_status = "incomplete"
        rows.append(
            {
                "contract_id": contract.contract_id,
                "source_id": source_id,
                "required_acquisition_count": required,
                "available_acquisition_count": available,
                "deferred_acquisition_count": deferred,
                "missing_acquisition_count": missing,
                "coverage_status": coverage_status,
                "notes": "local coverage scan only; missing rows require one-shot provider acquisition",
            }
        )
    return rows


def _coverage_output_root(data_root: Path, source_id: str, contract_id: str, month: str) -> Path:
    if source_id == "trading_economics_calendar_web":
        return data_root / "monthly_backfill" / source_id / month
    if source_id == "alpaca_bars" and "/" in month:
        target_ref, month_ref = month.split("/", 1)
        return data_root / "monthly_backfill" / source_id / target_ref.upper() / month_ref
    return data_root / "replay" / source_id / contract_id / month


def _coverage_receipt_path(
    *,
    data_root: Path,
    source_id: str,
    contract_id: str,
    suffix: str,
    source_output_root: Path,
) -> Path:
    if source_id == "trading_economics_calendar_web":
        canonical_root = data_root / "monthly_backfill" / source_id / suffix
        return _latest_succeeded_receipt(canonical_root) or (canonical_root / "completion_receipt.json")
    return source_output_root / "completion_receipt.json"


def _latest_succeeded_receipt(root: Path) -> Path | None:
    candidates = [root / "completion_receipt.json"]
    runs_root = root / "runs"
    if runs_root.exists():
        candidates.extend(sorted(runs_root.glob("*/completion_receipt.json")))
    succeeded: list[Path] = [path for path in candidates if _receipt_succeeded(path)]
    if not succeeded:
        return None
    return max(succeeded, key=lambda path: path.stat().st_mtime)


def _receipt_succeeded(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    runs = payload.get("runs") if isinstance(payload, Mapping) else None
    return isinstance(runs, list) and any(isinstance(run, Mapping) and run.get("status") == "succeeded" for run in runs)


def _expected_output_ref(source_id: str, contract_id: str, month: str) -> str:
    if source_id == "alpaca_bars" and "/" in month:
        target_ref, month_ref = month.split("/", 1)
        return f"storage://trading-data/monthly_backfill/{source_id}/{target_ref.upper()}/{month_ref}/"
    return f"storage://trading-data/replay/{source_id}/{contract_id}/{month}/"


def _acquisition_id(contract_id: str, source_id: str, month: str) -> str:
    return "rplacq_" + "_".join([_path_token(contract_id), _path_token(source_id), _path_token(month)])


def _path_token(value: str) -> str:
    return value.lower().replace("/", "_").replace("-", "_")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_coverage_summary(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _freeze_validation_errors(manifest: Mapping[str, Any], coverage_rows: Iterable[Mapping[str, str]]) -> list[str]:
    errors: list[str] = []
    if manifest.get("contract_type") != REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT:
        errors.append("dataset manifest contract_type is not replay_dataset_preparation_manifest")
    if manifest.get("freeze_status") not in {"not_frozen", "frozen"}:
        errors.append("dataset manifest freeze_status must be not_frozen or frozen")
    try:
        missing_count = int(manifest.get("missing_feed_acquisition_count", -1))
    except (TypeError, ValueError):
        missing_count = -1
    if missing_count != 0:
        errors.append(f"missing_feed_acquisition_count must be 0, got {manifest.get('missing_feed_acquisition_count')}")
    tradable_target_refs = _string_set(manifest.get("tradable_target_refs"))
    if not tradable_target_refs:
        errors.append("tradable_target_refs must include at least one live-equivalent replay target")

    rows = list(coverage_rows)
    if not rows:
        errors.append("coverage summary is empty")
    for row in rows:
        source_id = row.get("source_id", "")
        status = row.get("coverage_status", "")
        try:
            missing = int(row.get("missing_acquisition_count", "-1"))
        except ValueError:
            missing = -1
        if missing != 0:
            errors.append(f"{source_id} has missing_acquisition_count={row.get('missing_acquisition_count')}")
        if status == "complete":
            continue
        if status == "deferred" and source_id in ACCEPTED_DEFERRED_SOURCE_IDS:
            continue
        errors.append(f"{source_id} has non-freezable coverage_status={status}")
    errors.extend(_feed_acquisition_plan_validation_errors(manifest))
    return errors


def _feed_acquisition_plan_validation_errors(manifest: Mapping[str, Any]) -> list[str]:
    plan_ref = manifest.get("feed_acquisition_plan_ref")
    if not plan_ref:
        return []
    plan_path = Path(str(plan_ref))
    if not plan_path.exists():
        return [f"feed acquisition plan not found: {plan_ref}"]
    with plan_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    receipt_paths: dict[str, list[str]] = {}
    errors: list[str] = []
    for row in rows:
        source_id = row.get("source_id", "")
        coverage_status = row.get("coverage_status", "")
        receipt_path = row.get("coverage_receipt_path", "")
        acquisition_id = row.get("acquisition_id", "")
        if source_id in ACCEPTED_DEFERRED_SOURCE_IDS and not str(row.get("target_ref") or "").strip():
            errors.append(f"{acquisition_id} has no target_ref")
        if coverage_status == "deferred" and source_id in ACCEPTED_DEFERRED_SOURCE_IDS:
            continue
        if not receipt_path:
            errors.append(f"{acquisition_id} has no coverage_receipt_path")
            continue
        receipt_paths.setdefault(receipt_path, []).append(acquisition_id)
        if not _receipt_succeeded(Path(receipt_path)):
            errors.append(f"{acquisition_id} has no succeeded receipt at {receipt_path}")
    for path, acquisition_ids in sorted(receipt_paths.items()):
        if len(acquisition_ids) <= 1:
            continue
        suffix = "..." if len(acquisition_ids) > 5 else ""
        errors.append(
            f"coverage_receipt_path is shared by multiple non-deferred acquisitions: "
            f"{path} ({', '.join(acquisition_ids[:5])}{suffix})"
        )
    return errors


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return {stripped.upper()} if stripped else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().upper() for item in value if str(item).strip()}
    return set()


def _join(values: Iterable[str]) -> str:
    return ";".join(values)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "ACCEPTED_DEFERRED_SOURCE_IDS",
    "REPLAY_COVERAGE_SUMMARY_CONTRACT",
    "REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT",
    "REPLAY_DATASET_FREEZE_RECEIPT_CONTRACT",
    "REPLAY_FEED_ACQUISITION_PLAN_CONTRACT",
    "REPLAY_WINDOW_MANIFEST_CONTRACT",
    "FrozenReplayDataset",
    "PreparedReplayDataset",
    "freeze_replay_dataset",
    "prepare_replay_dataset",
]
