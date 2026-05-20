"""Benchmark dataset preparation manifests.

This module turns an accepted candidate-policy replay benchmark contract into
concrete storage-side preparation artifacts. It does not call providers, mutate
SQL, freeze the benchmark, select option contracts, or write active model state.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark import BenchmarkContract, validate_benchmark_contract

BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT = "benchmark_dataset_preparation_manifest"
BENCHMARK_REPLAY_WINDOW_MANIFEST_CONTRACT = "benchmark_replay_window_manifest"
BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT = "benchmark_feed_acquisition_plan"
BENCHMARK_COVERAGE_SUMMARY_CONTRACT = "benchmark_coverage_summary"
DEFAULT_OUTPUT_ROOT = Path("/root/projects/trading-storage/storage/benchmark")
DEFAULT_DATA_ROOT = Path("/root/projects/trading-storage/storage/data")
DEFAULT_SOURCE_CONTRACT_REF = "trading-evaluation/benchmarks/promotion_benchmark_candidate_policy_replay.json"

REPLAY_WINDOW_FIELDS = [
    "contract_id",
    "benchmark_mode",
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
class PreparedBenchmarkDataset:
    """Paths and summary for a prepared benchmark dataset manifest."""

    manifest_path: Path
    replay_window_manifest_path: Path
    feed_acquisition_plan_path: Path
    coverage_summary_path: Path
    manifest: dict[str, Any]

def prepare_benchmark_dataset(
    payload: Mapping[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    data_root: Path = DEFAULT_DATA_ROOT,
    source_contract_ref: str = DEFAULT_SOURCE_CONTRACT_REF,
    prepared_at_utc: str | None = None,
) -> PreparedBenchmarkDataset:
    """Write a benchmark dataset preparation bundle."""

    validation = validate_benchmark_contract(payload)
    if validation.validation_status != "passed" or validation.contract is None:
        raise ValueError("benchmark contract validation failed: " + "; ".join(validation.errors))

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
        "contract_type": BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT,
        "contract_id": contract.contract_id,
        "benchmark_mode": contract.benchmark_mode,
        "preparation_status": "prepared_candidate_policy_replay_acquisition_bundle",
        "freeze_status": "not_frozen",
        "prepared_at_utc": prepared_at,
        "source_contract_ref": source_contract_ref,
        "candidate_policy_ref": contract.candidate_policy_ref,
        "replay_route_ref": contract.replay_route_ref,
        "dataset_root": str(dataset_root),
        "storage_ref": f"storage://trading-storage/benchmark/{contract.contract_id}/",
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
            "benchmark_freeze_performed": False,
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

    return PreparedBenchmarkDataset(
        manifest_path=manifest_path,
        replay_window_manifest_path=replay_window_manifest_path,
        feed_acquisition_plan_path=feed_acquisition_plan_path,
        coverage_summary_path=coverage_summary_path,
        manifest=manifest,
    )


def _replay_window_rows(contract: BenchmarkContract) -> list[dict[str, Any]]:
    return [
        {
            "contract_id": contract.contract_id,
            "benchmark_mode": contract.benchmark_mode,
            "start_date": contract.start_date.isoformat(),
            "end_date": contract.end_date.isoformat(),
            "min_trading_days": contract.min_trading_days,
            "candidate_policy_ref": contract.candidate_policy_ref,
            "replay_route_ref": contract.replay_route_ref,
            "market_condition_tags": _join(contract.market_condition_tags),
            "selection_metric_refs": _join(contract.selection_metric_refs),
        }
    ]


def _acquisition_rows(contract: BenchmarkContract, *, data_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in _replay_sources():
        for window in _replay_months(contract):
            month = window["month"]
            acquisition_id = _acquisition_id(contract.contract_id, source["source_id"], month)
            source_output_root = _coverage_output_root(data_root, source["source_id"], contract.contract_id, month)
            receipt_path = source_output_root / "completion_receipt.json"
            params = _feed_params(contract, source, window)
            coverage_status = "available" if _receipt_succeeded(receipt_path) else "missing"
            rows.append(
                {
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
                    "expected_output_ref": _expected_output_ref(source["source_id"], contract.contract_id, month),
                    "coverage_status": coverage_status,
                    "coverage_receipt_path": str(receipt_path),
                    "params_json": json.dumps(params, sort_keys=True),
                    "notes": source["notes"],
                }
            )
    return rows


def _replay_sources() -> tuple[dict[str, str], ...]:
    return (
        {
            "source_id": "alpaca_bars",
            "feed": "01_feed_alpaca_bars",
            "timeframe": "1Day",
            "notes": "candidate-policy replay equity and ETF daily OHLCV surface",
        },
        {
            "source_id": "alpaca_liquidity",
            "feed": "02_feed_alpaca_liquidity",
            "timeframe": "1Min",
            "notes": "candidate-policy replay liquidity and spread surface for admitted candidates",
        },
        {
            "source_id": "alpaca_news",
            "feed": "03_feed_alpaca_news",
            "timeframe": "event_time",
            "notes": "candidate-policy replay symbol-scoped news evidence after point-in-time candidate admission",
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


def _feed_params(contract: BenchmarkContract, source: Mapping[str, str], window: Mapping[str, str]) -> dict[str, Any]:
    return {
        "contract_id": contract.contract_id,
        "candidate_policy_ref": contract.candidate_policy_ref,
        "replay_route_ref": contract.replay_route_ref,
        "start": window["start_date"],
        "end": window["end_date_exclusive"],
        "timeframe": source["timeframe"],
        "benchmark_acquisition_policy": "candidate_policy_replay_monthly_surface",
        "source_id": source["source_id"],
    }


def _replay_months(contract: BenchmarkContract) -> list[dict[str, str]]:
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


def _coverage_rows(contract: BenchmarkContract, acquisition_rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
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
    return data_root / "benchmark_replay" / source_id / contract_id / month


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
    return f"storage://trading-data/benchmark_replay/{source_id}/{contract_id}/{month}/"


def _acquisition_id(contract_id: str, source_id: str, month: str) -> str:
    return "bmkacq_" + "_".join([_path_token(contract_id), _path_token(source_id), month.replace("-", "_")])


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
    "BENCHMARK_COVERAGE_SUMMARY_CONTRACT",
    "BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT",
    "BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT",
    "BENCHMARK_REPLAY_WINDOW_MANIFEST_CONTRACT",
    "PreparedBenchmarkDataset",
    "prepare_benchmark_dataset",
]
