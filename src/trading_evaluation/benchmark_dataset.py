"""Benchmark dataset preparation manifests.

This module turns an accepted benchmark contract into concrete storage-side
preparation artifacts. It does not call providers, mutate SQL, freeze the
benchmark, select option contracts, or write active model state.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .benchmark import BenchmarkComponent, BenchmarkContract, validate_benchmark_contract

BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT = "benchmark_dataset_preparation_manifest"
BENCHMARK_COMPONENT_MANIFEST_CONTRACT = "benchmark_component_manifest"
BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT = "benchmark_feed_acquisition_plan"
BENCHMARK_COVERAGE_SUMMARY_CONTRACT = "benchmark_coverage_summary"
DEFAULT_OUTPUT_ROOT = Path("/root/projects/trading-storage/storage/benchmark")
DEFAULT_DATA_ROOT = Path("/root/projects/trading-data/storage")
DEFAULT_SOURCE_CONTRACT_REF = "trading-evaluation/benchmarks/primary_benchmark_candidate_20260519.json"
DEFAULT_SHARED_CSV_REF = "trading-storage/main/shared/evaluation_primary_benchmark_candidate.csv"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc

COMPONENT_FIELDS = [
    "contract_id", "component_id", "target_symbol", "asset_class", "theme_bucket", "component_role",
    "start_date", "end_date", "weight", "market_condition_tags", "data_availability_tags",
    "event_coverage_tags", "sector_coverage_tags", "target_context_ref", "stress_exception_ref",
]

ACQUISITION_FIELDS = [
    "acquisition_id", "contract_id", "component_id", "target_symbol", "asset_class", "source_id", "feed",
    "month", "start_date", "end_date_exclusive", "timeframe", "acquisition_mode", "output_root",
    "expected_output_ref", "coverage_status", "coverage_receipt_path", "params_json", "notes",
]

COVERAGE_FIELDS = [
    "contract_id", "component_id", "target_symbol", "source_id", "required_acquisition_count",
    "available_acquisition_count", "deferred_acquisition_count", "missing_acquisition_count", "coverage_status", "notes",
]


@dataclass(frozen=True)
class PreparedBenchmarkDataset:
    """Paths and summary for a prepared benchmark dataset manifest."""

    manifest_path: Path
    component_manifest_path: Path
    feed_acquisition_plan_path: Path
    coverage_summary_path: Path
    manifest: dict[str, Any]


def prepare_benchmark_dataset(
    payload: Mapping[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    data_root: Path = DEFAULT_DATA_ROOT,
    source_contract_ref: str = DEFAULT_SOURCE_CONTRACT_REF,
    shared_candidate_csv_ref: str = DEFAULT_SHARED_CSV_REF,
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

    component_rows = _component_rows(contract)
    acquisition_rows = _acquisition_rows(contract, data_root=data_root)
    coverage_rows = _coverage_rows(contract, acquisition_rows)

    component_manifest_path = dataset_root / "component_manifest.csv"
    feed_acquisition_plan_path = dataset_root / "feed_acquisition_plan.csv"
    coverage_summary_path = dataset_root / "coverage_summary.csv"
    manifest_path = dataset_root / "dataset_manifest.json"

    _write_csv(component_manifest_path, COMPONENT_FIELDS, component_rows)
    _write_csv(feed_acquisition_plan_path, ACQUISITION_FIELDS, acquisition_rows)
    _write_csv(coverage_summary_path, COVERAGE_FIELDS, coverage_rows)

    manifest = {
        "contract_type": BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT,
        "contract_id": contract.contract_id,
        "preparation_status": "prepared_one_shot_acquisition_bundle",
        "freeze_status": "not_frozen",
        "prepared_at_utc": prepared_at,
        "source_contract_ref": source_contract_ref,
        "shared_candidate_csv_ref": shared_candidate_csv_ref,
        "dataset_root": str(dataset_root),
        "storage_ref": f"storage://trading-storage/benchmark/{contract.contract_id}/",
        "component_count": len(component_rows),
        "feed_acquisition_count": len(acquisition_rows),
        "available_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "available"),
        "deferred_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "deferred"),
        "missing_feed_acquisition_count": sum(1 for row in acquisition_rows if row["coverage_status"] == "missing"),
        "component_manifest_ref": str(component_manifest_path),
        "feed_acquisition_plan_ref": str(feed_acquisition_plan_path),
        "coverage_summary_ref": str(coverage_summary_path),
        "artifact_refs": [str(component_manifest_path), str(feed_acquisition_plan_path), str(coverage_summary_path)],
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
            "option_contract_selection_required_before_thetadata_selected_contract_feeds",
            "sec_cik_mapping_required_before_sec_company_financial_acquisition",
            "crypto_historical_quote_order_book_context_remains_accepted_missing_data_stress",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return PreparedBenchmarkDataset(
        manifest_path=manifest_path,
        component_manifest_path=component_manifest_path,
        feed_acquisition_plan_path=feed_acquisition_plan_path,
        coverage_summary_path=coverage_summary_path,
        manifest=manifest,
    )


def _component_rows(contract: BenchmarkContract) -> list[dict[str, Any]]:
    return [
        {
            "contract_id": contract.contract_id,
            "component_id": component.component_id,
            "target_symbol": component.target_symbol,
            "asset_class": component.asset_class,
            "theme_bucket": component.theme_bucket,
            "component_role": component.component_role,
            "start_date": component.start_date.isoformat(),
            "end_date": component.end_date.isoformat(),
            "weight": _format_weight(component.weight),
            "market_condition_tags": _join(component.market_condition_tags),
            "data_availability_tags": _join(component.data_availability_tags),
            "event_coverage_tags": _join(component.event_coverage_tags),
            "sector_coverage_tags": _join(component.sector_coverage_tags),
            "target_context_ref": component.target_context_ref,
            "stress_exception_ref": component.stress_exception_ref,
        }
        for component in contract.benchmark_components
    ]


def _acquisition_rows(contract: BenchmarkContract, *, data_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for component in contract.benchmark_components:
        for source in _component_sources(component):
            for window in _component_months(component):
                acquisition_id = _acquisition_id(contract.contract_id, component, source["source_id"], window["month"])
                source_output_root = _coverage_output_root(data_root, source["source_id"], component.target_symbol, window["month"])
                receipt_path = _coverage_receipt_path(data_root, source["source_id"], component.target_symbol, window["month"])
                params = _feed_params(component, source, window)
                if _receipt_succeeded(receipt_path, required_params=_required_receipt_params(source["source_id"], params)):
                    coverage_status = "available"
                elif source.get("deferred_without_receipt") == "true":
                    coverage_status = "deferred"
                else:
                    coverage_status = "missing"
                rows.append(
                    {
                        "acquisition_id": acquisition_id,
                        "contract_id": contract.contract_id,
                        "component_id": component.component_id,
                        "target_symbol": component.target_symbol,
                        "asset_class": component.asset_class,
                        "source_id": source["source_id"],
                        "feed": source["feed"],
                        "month": window["month"],
                        "start_date": window["start_date"],
                        "end_date_exclusive": window["end_date_exclusive"],
                        "timeframe": source["timeframe"],
                        "acquisition_mode": "one_shot_benchmark_acquisition",
                        "output_root": str(source_output_root),
                        "expected_output_ref": _expected_output_ref(source["source_id"], component.target_symbol, window["month"]),
                        "coverage_status": coverage_status,
                        "coverage_receipt_path": str(receipt_path),
                        "params_json": json.dumps(params, sort_keys=True),
                        "notes": source["notes"],
                    }
                )
    return rows


def _component_sources(component: BenchmarkComponent) -> tuple[dict[str, str], ...]:
    if component.asset_class.startswith("crypto"):
        return (
            {
                "source_id": "okx_crypto_market_data",
                "feed": "04_feed_okx_crypto_market_data",
                "timeframe": "1Day",
                "notes": "historical crypto daily candles; quote/order-book context remains missing by accepted stress policy",
            },
        )
    if component.asset_class in {"equity_single_name", "equity_etf"}:
        return (
            {
                "source_id": "alpaca_bars",
                "feed": "01_feed_alpaca_bars",
                "timeframe": "1Day",
                "notes": "daily underlying OHLCV for component window",
            },
            {
                "source_id": "alpaca_liquidity",
                "feed": "02_feed_alpaca_liquidity",
                "timeframe": "1Min",
                "notes": "benchmark one-shot full trade/quote liquidity acquisition by hourly regular-session windows; raw trades and quotes remain transient",
            },
            {
                "source_id": "alpaca_news",
                "feed": "03_feed_alpaca_news",
                "timeframe": "event_time",
                "notes": "symbol-scoped event/news evidence for event coverage review",
            },
        )
    return ()


def _feed_params(component: BenchmarkComponent, source: Mapping[str, str], window: Mapping[str, str]) -> dict[str, Any]:
    feed = source["feed"]
    if feed == "01_feed_alpaca_bars":
        return {
            "symbol": component.target_symbol,
            "start": window["start_date"],
            "end": window["end_date_exclusive"],
            "timeframe": source["timeframe"],
            "adjustment": "raw",
            "limit": 10000,
            "max_pages": 50,
        }
    if feed == "02_feed_alpaca_liquidity":
        acquisition_windows = _liquidity_acquisition_windows(window)
        return {
            "symbol": component.target_symbol,
            "start": window["start_date"],
            "end": window["end_date_exclusive"],
            "timeframe": source["timeframe"],
            "limit": 10000,
            "max_pages": 500,
            "acquisition_windows": acquisition_windows,
            "benchmark_liquidity_acquisition_policy": "full_hourly_regular_session_windows_per_component_month",
            "fail_on_incomplete_pagination": True,
        }
    if feed == "03_feed_alpaca_news":
        return {
            "symbols": [component.target_symbol],
            "start": window["start_date"],
            "end": window["end_date_exclusive"],
            "limit": 50,
            "max_pages": 20,
        }
    if feed == "04_feed_okx_crypto_market_data":
        return {
            "instId": component.target_symbol,
            "timeframe": source["timeframe"],
            "limit": 300,
            "benchmark_window_start": window["start_date"],
            "benchmark_window_end_exclusive": window["end_date_exclusive"],
            "historical_window_status": "prepared_requirement_current_okx_feed_does_not_persist_quote_order_book_context",
        }
    return {}


def _component_months(component: BenchmarkComponent) -> list[dict[str, str]]:
    current = date(component.start_date.year, component.start_date.month, 1)
    end_month = date(component.end_date.year, component.end_date.month, 1)
    windows: list[dict[str, str]] = []
    while current <= end_month:
        next_month = _next_month(current)
        start = max(component.start_date, current)
        end = min(component.end_date, next_month)
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


def _liquidity_acquisition_windows(window: Mapping[str, str]) -> list[dict[str, str]]:
    start_date = date.fromisoformat(window["start_date"])
    end_date = date.fromisoformat(window["end_date_exclusive"])
    windows: list[dict[str, str]] = []
    current = start_date
    while current < end_date:
        if current.weekday() < 5:
            session_start = datetime.combine(current, time(9, 30), tzinfo=ET)
            session_end = datetime.combine(current, time(16, 0), tzinfo=ET)
            chunk_start = session_start
            while chunk_start < session_end:
                chunk_end = min(chunk_start + timedelta(hours=1), session_end)
                windows.append(
                    {
                        "label": (
                            f"{current.isoformat()}_"
                            f"{chunk_start.strftime('%H%M')}_{chunk_end.strftime('%H%M')}_et"
                        ),
                        "start": chunk_start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                        "end": chunk_end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    }
                )
                chunk_start = chunk_end
        current += timedelta(days=1)
    return windows


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _coverage_rows(contract: BenchmarkContract, acquisition_rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for row in acquisition_rows:
        grouped.setdefault((row["component_id"], row["source_id"]), []).append(row)
    rows: list[dict[str, Any]] = []
    component_by_id = {component.component_id: component for component in contract.benchmark_components}
    for component_id, source_id in sorted(grouped):
        source_rows = grouped[(component_id, source_id)]
        available = sum(1 for row in source_rows if row["coverage_status"] == "available")
        deferred = sum(1 for row in source_rows if row["coverage_status"] == "deferred")
        missing = sum(1 for row in source_rows if row["coverage_status"] == "missing")
        required = len(source_rows)
        component = component_by_id[component_id]
        if available == required:
            coverage_status = "complete"
        elif available + deferred == required:
            coverage_status = "deferred"
        else:
            coverage_status = "incomplete"
        rows.append(
            {
                "contract_id": contract.contract_id,
                "component_id": component_id,
                "target_symbol": component.target_symbol,
                "source_id": source_id,
                "required_acquisition_count": required,
                "available_acquisition_count": available,
                "deferred_acquisition_count": deferred,
                "missing_acquisition_count": missing,
                "coverage_status": coverage_status,
                "notes": "local coverage scan only; missing rows require one-shot provider acquisition or accepted stress exception",
            }
        )
    return rows


def _coverage_receipt_path(data_root: Path, source_id: str, symbol: str, month: str) -> Path:
    return _coverage_output_root(data_root, source_id, symbol, month) / "completion_receipt.json"


def _coverage_output_root(data_root: Path, source_id: str, symbol: str, month: str) -> Path:
    return data_root / "monthly_backfill" / source_id / symbol.upper() / month


def _required_receipt_params(source_id: str, plan_params: Mapping[str, Any]) -> dict[str, Any] | None:
    if source_id == "alpaca_liquidity":
        return {
            "benchmark_liquidity_acquisition_policy": "full_hourly_regular_session_windows_per_component_month",
            "required_acquisition_window_labels": [
                str(window.get("label"))
                for window in plan_params.get("acquisition_windows", [])
                if isinstance(window, Mapping) and window.get("label")
            ],
        }
    return None


def _receipt_succeeded(path: Path, *, required_params: Mapping[str, Any] | None = None) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    runs = payload.get("runs") if isinstance(payload, Mapping) else None
    if not isinstance(runs, list):
        return False
    required_labels = set(required_params.get("required_acquisition_window_labels", [])) if required_params else set()
    observed_labels: set[str] = set()
    for run in runs:
        if not isinstance(run, Mapping) or run.get("status") != "succeeded":
            continue
        if not required_params:
            return True
        output_dir = run.get("output_dir")
        if not output_dir:
            continue
        manifest_path = Path(str(output_dir)) / "request_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        params = manifest.get("params") if isinstance(manifest, Mapping) else None
        if not isinstance(params, Mapping):
            continue
        scalar_requirements = {
            key: value
            for key, value in required_params.items()
            if key != "required_acquisition_window_labels"
        }
        if not all(params.get(key) == value for key, value in scalar_requirements.items()):
            continue
        if not required_labels:
            return True
        for window in params.get("acquisition_windows", []):
            if isinstance(window, Mapping) and window.get("label"):
                observed_labels.add(str(window["label"]))
    return bool(required_labels) and required_labels.issubset(observed_labels)


def _expected_output_ref(source_id: str, symbol: str, month: str) -> str:
    return f"storage://trading-data/monthly_backfill/{source_id}/{symbol.upper()}/{month}/"


def _acquisition_id(contract_id: str, component: BenchmarkComponent, source_id: str, month: str) -> str:
    return "bmkacq_" + "_".join(
        [
            _path_token(contract_id),
            _path_token(component.component_id),
            _path_token(source_id),
            component.target_symbol.lower().replace("-", "_"),
            month.replace("-", "_"),
        ]
    )


def _path_token(value: str) -> str:
    return value.lower().replace("/", "_").replace("-", "_")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _format_weight(value: float) -> str:
    return f"{value:.10g}"


def _join(values: Iterable[str]) -> str:
    return ";".join(values)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "BENCHMARK_COMPONENT_MANIFEST_CONTRACT",
    "BENCHMARK_COVERAGE_SUMMARY_CONTRACT",
    "BENCHMARK_DATASET_PREPARATION_MANIFEST_CONTRACT",
    "BENCHMARK_FEED_ACQUISITION_PLAN_CONTRACT",
    "PreparedBenchmarkDataset",
    "prepare_benchmark_dataset",
]
