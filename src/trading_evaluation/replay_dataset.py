"""Replay dataset preparation manifests.

This module turns an accepted candidate-policy replay contract into
concrete storage-side preparation artifacts. It does not call providers, mutate
SQL, freeze the replay, select option contracts, or write active model state.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .replay import ReplayContract, validate_replay_contract

REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT = "replay_dataset_preparation_manifest"
REPLAY_WINDOW_MANIFEST_CONTRACT = "replay_window_manifest"
REPLAY_FEED_ACQUISITION_PLAN_CONTRACT = "replay_feed_acquisition_plan"
REPLAY_COVERAGE_SUMMARY_CONTRACT = "replay_coverage_summary"
DEFAULT_OUTPUT_ROOT = Path("/root/projects/trading-storage/storage/05_replay_datasets")
DEFAULT_DATA_ROOT = Path("/root/projects/trading-storage/storage/01_source_data")
DEFAULT_SOURCE_CONTRACT_REF = "trading-evaluation/replays/promotion_replay_candidate_policy.json"
CRYPTO_SPOT_INSTRUMENT_REFS = ("BTC-USDT", "ETH-USDT", "SOL-USDT")

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
    prepared_at = prepared_at_utc or _now_utc()
    dataset_root = output_root / contract.contract_id
    dataset_root.mkdir(parents=True, exist_ok=True)

    replay_window_rows = _replay_window_rows(contract)
    acquisition_rows = _acquisition_rows(contract, data_root=data_root)
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
            "candidate_universe_materializes_point_in_time_during_replay",
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


def _acquisition_rows(contract: ReplayContract, *, data_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in _replay_sources():
        for window in _replay_months(contract):
            rows.extend(_acquisition_rows_for_source_window(contract, source, window, data_root=data_root))
    return rows


def _acquisition_rows_for_source_window(
    contract: ReplayContract,
    source: Mapping[str, str],
    window: Mapping[str, str],
    *,
    data_root: Path,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    month = window["month"]
    if source["source_id"] == "okx_crypto_market_data":
        for instrument_ref in CRYPTO_SPOT_INSTRUMENT_REFS:
            rows.append(
                _acquisition_row(
                    contract,
                    source,
                    window,
                    data_root=data_root,
                    acquisition_suffix=instrument_ref.lower().replace("-", "_"),
                    params_extra={"instId": instrument_ref},
                    notes_suffix=f"; fixed crypto spot instrument {instrument_ref}",
                )
            )
        return rows
    if source.get("candidate_dependent") == "true":
        rows.append(
            _acquisition_row(
                contract,
                source,
                window,
                data_root=data_root,
                coverage_status_override="deferred",
                params_extra={
                    "candidate_symbol_policy": "materialize_point_in_time_during_replay",
                    "candidate_symbol_source": contract.candidate_policy_ref,
                },
                notes_suffix="; deferred until replay candidate symbols materialize",
            )
        )
        return rows
    rows.append(_acquisition_row(contract, source, window, data_root=data_root, acquisition_suffix=month))
    return rows


def _acquisition_row(
    contract: ReplayContract,
    source: Mapping[str, str],
    window: Mapping[str, str],
    *,
    data_root: Path,
    acquisition_suffix: str | None = None,
    coverage_status_override: str | None = None,
    params_extra: Mapping[str, Any] | None = None,
    notes_suffix: str = "",
) -> dict[str, str]:
    month = window["month"]
    suffix = acquisition_suffix or month
    acquisition_id = _acquisition_id(contract.contract_id, source["source_id"], suffix)
    source_output_root = _coverage_output_root(data_root, source["source_id"], contract.contract_id, suffix)
    receipt_path = source_output_root / "completion_receipt.json"
    params = _feed_params(contract, source, window)
    params.update(dict(params_extra or {}))
    coverage_status = coverage_status_override or ("available" if _receipt_succeeded(receipt_path) else "missing")
    return {
        "acquisition_id": acquisition_id,
        "contract_id": contract.contract_id,
        "source_id": source["source_id"],
        "feed": source["feed"],
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
            "notes": "candidate-policy replay equity and ETF daily OHLCV surface",
            "candidate_dependent": "true",
        },
        {
            "source_id": "alpaca_liquidity",
            "feed": "02_feed_alpaca_liquidity",
            "timeframe": "1Min",
            "notes": "candidate-policy replay liquidity and spread surface for admitted candidates",
            "candidate_dependent": "true",
        },
        {
            "source_id": "alpaca_news",
            "feed": "03_feed_alpaca_news",
            "timeframe": "event_time",
            "notes": "candidate-policy replay symbol-scoped news evidence after point-in-time candidate admission",
            "candidate_dependent": "true",
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
        "candidate_policy_ref": contract.candidate_policy_ref,
        "replay_route_ref": contract.replay_route_ref,
        "start": window["start_date"],
        "end": window["end_date_exclusive"],
        "timeframe": source["timeframe"],
        "replay_acquisition_policy": "candidate_policy_replay_monthly_surface",
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
    if source["source_id"] == "okx_crypto_market_data":
        params.update({"limit": 100, "max_pages": 1})
    return params


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
    return data_root / "replay" / source_id / contract_id / month


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
    return f"storage://trading-data/replay/{source_id}/{contract_id}/{month}/"


def _acquisition_id(contract_id: str, source_id: str, month: str) -> str:
    return "rplacq_" + "_".join([_path_token(contract_id), _path_token(source_id), month.replace("-", "_")])


def _path_token(value: str) -> str:
    return value.lower().replace("/", "_").replace("-", "_")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _join(values: Iterable[str]) -> str:
    return ";".join(values)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "REPLAY_COVERAGE_SUMMARY_CONTRACT",
    "REPLAY_DATASET_PREPARATION_MANIFEST_CONTRACT",
    "REPLAY_FEED_ACQUISITION_PLAN_CONTRACT",
    "REPLAY_WINDOW_MANIFEST_CONTRACT",
    "PreparedReplayDataset",
    "prepare_replay_dataset",
]
