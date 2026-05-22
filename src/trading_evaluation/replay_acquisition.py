"""One-shot replay acquisition runner.

The runner consumes a prepared replay feed_acquisition_plan.csv and can
materialize or execute bounded feed task payloads. It does not create manager
requests, mutate SQL, freeze replay contracts, train models, activate models, call
brokers, or mutate accounts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_DATA_ROOT = Path("/root/projects/trading-data")
DEFAULT_DATASET_ROOT = Path("/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy")
DEFAULT_RUN_ID = "replay_one_shot_acquisition"
TRADING_MANAGER_SRC = Path("/root/projects/trading-manager/src")

MODULE_BY_FEED = {
    "01_feed_alpaca_bars": "data_feed.01_feed_alpaca_bars",
    "02_feed_alpaca_liquidity": "data_feed.02_feed_alpaca_liquidity",
    "03_feed_alpaca_news": "data_feed.03_feed_alpaca_news",
    "04_feed_okx_crypto_market_data": "data_feed.04_feed_okx_crypto_market_data",
    "05_feed_gdelt_news": "data_feed.05_feed_gdelt_news",
    "07_feed_trading_economics_calendar_web": "data_feed.07_feed_trading_economics_calendar_web",
    "08_feed_sec_company_financials": "data_feed.08_feed_sec_company_financials",
    "09_feed_thetadata_option_selection_snapshot": "data_feed.09_feed_thetadata_option_selection_snapshot",
}

PROVIDER_CONTROLS_BY_FEED = {
    "01_feed_alpaca_bars": {"allowed_providers": ["alpaca"], "allowed_endpoint_families": ["bars"], "max_time_window": "45d"},
    "02_feed_alpaca_liquidity": {"allowed_providers": ["alpaca"], "allowed_endpoint_families": ["trades_quotes"], "max_time_window": "45d"},
    "03_feed_alpaca_news": {"allowed_providers": ["alpaca"], "allowed_endpoint_families": ["news"], "max_time_window": "45d"},
    "04_feed_okx_crypto_market_data": {"allowed_providers": ["okx"], "allowed_endpoint_families": ["market_data"], "max_time_window": "370d"},
    "05_feed_gdelt_news": {"allowed_providers": ["gdelt_bigquery"], "allowed_endpoint_families": ["news_query"], "max_time_window": "45d"},
    "07_feed_trading_economics_calendar_web": {"allowed_providers": ["trading_economics"], "allowed_endpoint_families": ["calendar_web"], "max_time_window": "45d"},
    "08_feed_sec_company_financials": {"allowed_providers": ["sec_edgar"], "allowed_endpoint_families": ["company_financials"]},
    "09_feed_thetadata_option_selection_snapshot": {"allowed_providers": ["thetadata"], "allowed_endpoint_families": ["option_selection_snapshot"], "max_time_window": "1d"},
}

EXTRA_PYTHONPATH_BY_FEED = {
    "05_feed_gdelt_news": [TRADING_MANAGER_SRC],
}


@dataclass(frozen=True)
class AcquisitionItem:
    acquisition_id: str
    feed: str
    source_id: str
    month: str
    coverage_status: str
    output_root: str
    params: dict[str, Any]


@dataclass(frozen=True)
class RunnerItemResult:
    acquisition_id: str
    source_id: str
    feed: str
    month: str
    task_key_path: str
    command: list[str]
    execute: bool
    return_code: int | None
    status: str
    attempt_count: int = 0


@dataclass(frozen=True)
class RunnerSummary:
    contract_type: str
    dataset_root: str
    plan_path: str
    run_id: str
    selected_count: int
    executed_count: int
    succeeded_count: int
    failed_count: int
    task_key_root: str
    progress_log_path: str
    provider_calls_allowed: bool
    manager_request_route_used: bool
    sql_mutation_performed: bool
    model_activation_performed: bool
    broker_execution_performed: bool
    account_mutation_performed: bool
    items: tuple[RunnerItemResult, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [asdict(item) for item in self.items]
        return payload


def load_plan(plan_path: Path) -> list[AcquisitionItem]:
    items: list[AcquisitionItem] = []
    with plan_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            items.append(
                AcquisitionItem(
                    acquisition_id=str(row["acquisition_id"]),
                    feed=str(row["feed"]),
                    source_id=str(row["source_id"]),
                    month=str(row["month"]),
                    coverage_status=str(row["coverage_status"]),
                    output_root=str(row["output_root"]),
                    params=json.loads(row["params_json"]),
                )
            )
    return items


def select_items(
    items: Iterable[AcquisitionItem],
    *,
    source_ids: set[str],
    include_available: bool,
    include_deferred: bool = False,
    limit: int | None,
) -> list[AcquisitionItem]:
    selected: list[AcquisitionItem] = []
    for item in items:
        if source_ids and item.source_id not in source_ids:
            continue
        if not include_available and item.coverage_status == "available":
            continue
        if not include_deferred and item.coverage_status == "deferred":
            continue
        selected.append(item)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def _request_budget(params: Mapping[str, Any], feed: str) -> tuple[int, int | None, int]:
    max_pages = int(params.get("max_pages", 1) or 1)
    limit = int(params.get("limit", params.get("max_rows", 1000)) or 1000)
    if feed == "02_feed_alpaca_liquidity":
        windows = params.get("acquisition_windows") if isinstance(params.get("acquisition_windows"), list) else [None]
        return max_pages * 2 * len(windows), limit * max_pages * 2 * len(windows), 1
    if feed == "09_feed_thetadata_option_selection_snapshot":
        return 4, None, 1
    return max_pages, limit * max_pages, 1


def build_task_payload(item: AcquisitionItem, *, allow_provider_calls: bool = False) -> dict[str, Any]:
    controls = dict(PROVIDER_CONTROLS_BY_FEED.get(item.feed, {}))
    max_requests, max_rows, max_symbols = _request_budget(item.params, item.feed)
    controls.update(
        {
            "allow_live_provider_calls": allow_provider_calls,
            "autonomous_historical_provider_acquisition": allow_provider_calls,
            "secrets_policy": "secret_aliases_only",
            "max_requests": max_requests,
            "max_symbols": max_symbols,
            "replay_acquisition_id": item.acquisition_id,
        }
    )
    if max_rows is not None:
        controls["max_rows"] = max_rows
    return {
        "task_id": item.acquisition_id,
        "feed": item.feed,
        "source_id": item.source_id,
        "params": item.params,
        "output_root": item.output_root,
        "manager_controls": controls,
    }


def _run_id(base_run_id: str, item: AcquisitionItem) -> str:
    safe_id = item.acquisition_id.replace("/", "_").replace(":", "_")
    return f"{base_run_id}_{safe_id}"


def _feed_max_attempts(feed: str, te_max_attempts: int) -> int:
    if feed == "07_feed_trading_economics_calendar_web":
        return max(1, te_max_attempts)
    return 1


def run_acquisition(
    *,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    data_root: Path = DEFAULT_DATA_ROOT,
    run_id: str = DEFAULT_RUN_ID,
    source_ids: set[str] | None = None,
    include_available: bool = False,
    include_deferred: bool = False,
    limit: int | None = None,
    execute: bool = False,
    stop_on_failure: bool = False,
    te_max_attempts: int = 2,
    te_retry_delay_seconds: int = 60,
) -> RunnerSummary:
    plan_path = dataset_root / "feed_acquisition_plan.csv"
    items = select_items(
        load_plan(plan_path),
        source_ids=set(source_ids or []),
        include_available=include_available,
        include_deferred=include_deferred,
        limit=limit,
    )
    task_key_root = dataset_root / "acquisition_task_keys" / run_id
    progress_root = dataset_root / "acquisition_runs"
    task_key_root.mkdir(parents=True, exist_ok=True)
    progress_root.mkdir(parents=True, exist_ok=True)
    progress_log_path = progress_root / f"{run_id}.jsonl"
    results: list[RunnerItemResult] = []
    for item in items:
        module = MODULE_BY_FEED.get(item.feed)
        if module is None:
            result = RunnerItemResult(item.acquisition_id, item.source_id, item.feed, item.month, "", [], execute, None, "unsupported_feed")
            results.append(result)
            _append_progress(progress_log_path, result)
            if stop_on_failure:
                break
            continue
        payload = build_task_payload(item, allow_provider_calls=execute)
        task_key_path = task_key_root / f"{item.acquisition_id}.json"
        task_key_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        command = [sys.executable, "-m", module, str(task_key_path), "--run-id", _run_id(run_id, item)]
        return_code: int | None = None
        status = "planned"
        attempt_count = 0
        if execute:
            env = dict(os.environ)
            pythonpath_parts = [str(data_root / "src")]
            pythonpath_parts.extend(str(path) for path in EXTRA_PYTHONPATH_BY_FEED.get(item.feed, []) if path.exists())
            existing_pythonpath = env.get("PYTHONPATH")
            if existing_pythonpath:
                pythonpath_parts.append(existing_pythonpath)
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
            max_attempts = _feed_max_attempts(item.feed, te_max_attempts)
            for attempt in range(1, max_attempts + 1):
                attempt_count = attempt
                if attempt > 1 and te_retry_delay_seconds > 0:
                    time.sleep(te_retry_delay_seconds)
                attempt_run_id = _run_id(run_id, item) if attempt == 1 else f"{_run_id(run_id, item)}_attempt_{attempt}"
                command = [sys.executable, "-m", module, str(task_key_path), "--run-id", attempt_run_id]
                completed = subprocess.run(command, cwd=data_root, env=env)
                return_code = completed.returncode
                if return_code == 0:
                    break
            status = "succeeded" if return_code == 0 else "failed"
        result = RunnerItemResult(item.acquisition_id, item.source_id, item.feed, item.month, str(task_key_path), command, execute, return_code, status, attempt_count)
        results.append(result)
        _append_progress(progress_log_path, result)
        if execute and return_code != 0 and stop_on_failure:
            break
    return RunnerSummary(
        contract_type="replay_one_shot_acquisition_runner_summary",
        dataset_root=str(dataset_root),
        plan_path=str(plan_path),
        run_id=run_id,
        selected_count=len(items),
        executed_count=sum(1 for item in results if item.execute),
        succeeded_count=sum(1 for item in results if item.status == "succeeded"),
        failed_count=sum(1 for item in results if item.status in {"failed", "unsupported_feed"}),
        task_key_root=str(task_key_root),
        progress_log_path=str(progress_log_path),
        provider_calls_allowed=execute,
        manager_request_route_used=False,
        sql_mutation_performed=False,
        model_activation_performed=False,
        broker_execution_performed=False,
        account_mutation_performed=False,
        items=tuple(results),
    )


def _append_progress(path: Path, result: RunnerItemResult) -> None:
    row = asdict(result)
    row["recorded_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute replay one-shot feed acquisitions.")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--include-available", action="store_true")
    parser.add_argument("--include-deferred", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--te-max-attempts", type=int, default=2)
    parser.add_argument("--te-retry-delay-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    summary = run_acquisition(
        dataset_root=args.dataset_root,
        data_root=args.data_root,
        run_id=args.run_id,
        source_ids=set(args.source_id),
        include_available=args.include_available,
        include_deferred=args.include_deferred,
        limit=args.limit,
        execute=args.execute,
        stop_on_failure=args.stop_on_failure,
        te_max_attempts=args.te_max_attempts,
        te_retry_delay_seconds=args.te_retry_delay_seconds,
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 1 if summary.failed_count and args.execute else 0


__all__ = ["RunnerSummary", "build_task_payload", "load_plan", "run_acquisition", "select_items"]
