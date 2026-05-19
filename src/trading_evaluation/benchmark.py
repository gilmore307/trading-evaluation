"""Benchmark contract validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

REQUIRED_MARKET_CONDITION_TAGS = 4
MAX_STRESS_COMPONENT_WEIGHT = 0.15
MIN_SINGLE_NAME_COMPONENT_WEIGHT = 0.55
MAX_ETF_COMPONENT_WEIGHT = 0.30
MAX_CRYPTO_COMPONENT_WEIGHT = 0.15
KNOWN_COMPONENT_ROLES = {"primary", "stress_edge_case", "guardrail_stress"}
STRESS_COMPONENT_ROLES = {"stress_edge_case", "guardrail_stress"}
TARGET_CONTEXT_EXCEPTION_TAGS = {"missing_layer2_context", "intentionally_no_target_context"}
CRITICAL_DATA_STRESS_TAGS = {"missing_quote_order_book_context", "missing_layer2_context", "intentionally_no_target_context"}
KNOWN_DATA_AVAILABILITY_TAGS = {
    "full_ohlcv",
    "trade_derived_liquidity_only",
    "missing_quote_order_book_context",
    "missing_layer2_context",
    "sparse_bars",
    "thin_liquidity",
    "halt_or_suspension",
    "event_gap",
    "partial_event_coverage",
    "intentionally_no_target_context",
}


def _parse_date(value: object, *, field_name: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(frozen=True)
class BenchmarkComponent:
    """One blinded component inside a frozen benchmark panel."""

    component_id: str
    target_symbol: str
    asset_class: str
    theme_bucket: str
    component_role: str
    start_date: date
    end_date: date
    weight: float
    market_condition_tags: tuple[str, ...]
    data_availability_tags: tuple[str, ...]
    target_context_ref: str
    stress_exception_ref: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, fallback_id: str = "component_1") -> "BenchmarkComponent":
        try:
            weight = float(payload.get("weight", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("benchmark component weight must be numeric") from exc
        return cls(
            component_id=str(payload.get("component_id") or fallback_id).strip(),
            target_symbol=str(payload.get("target_symbol") or "").strip().upper(),
            asset_class=str(payload.get("asset_class") or "").strip(),
            theme_bucket=str(payload.get("theme_bucket") or "").strip(),
            component_role=str(payload.get("component_role") or "primary").strip(),
            start_date=_parse_date(payload.get("start_date"), field_name="component.start_date"),
            end_date=_parse_date(payload.get("end_date"), field_name="component.end_date"),
            weight=weight,
            market_condition_tags=_strings(payload.get("market_condition_tags") or ()),
            data_availability_tags=_strings(payload.get("data_availability_tags") or ()),
            target_context_ref=str(payload.get("target_context_ref") or "").strip(),
            stress_exception_ref=str(payload.get("stress_exception_ref") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "target_symbol": self.target_symbol,
            "asset_class": self.asset_class,
            "theme_bucket": self.theme_bucket,
            "component_role": self.component_role,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "weight": self.weight,
            "market_condition_tags": list(self.market_condition_tags),
            "data_availability_tags": list(self.data_availability_tags),
            "target_context_ref": self.target_context_ref,
            "stress_exception_ref": self.stress_exception_ref,
        }


@dataclass(frozen=True)
class BenchmarkContract:
    """Frozen primary benchmark panel contract."""

    contract_id: str
    target_symbol: str
    start_date: date
    end_date: date
    benchmark_components: tuple[BenchmarkComponent, ...]
    min_trading_days: int
    market_condition_tags: tuple[str, ...]
    data_snapshot_ref: str
    cost_model_ref: str
    baseline_refs: tuple[str, ...]
    training_universe_symbols: tuple[str, ...]
    excluded_training_windows: tuple[dict[str, Any], ...]
    guardrail_refs: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BenchmarkContract":
        try:
            min_trading_days = int(payload.get("min_trading_days", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("min_trading_days must be an integer") from exc
        windows = payload.get("excluded_training_windows") or []
        if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)):
            windows = []
        raw_components = payload.get("benchmark_components") or []
        if not isinstance(raw_components, Sequence) or isinstance(raw_components, (str, bytes)):
            raw_components = []
        components = tuple(
            BenchmarkComponent.from_mapping(component, fallback_id=f"component_{index}")
            for index, component in enumerate(raw_components, start=1)
            if isinstance(component, Mapping)
        )
        target_symbol = str(payload.get("target_symbol") or "").strip().upper()
        start_date = _parse_date(payload.get("start_date"), field_name="start_date")
        end_date = _parse_date(payload.get("end_date"), field_name="end_date")
        if not components and target_symbol:
            components = (
                BenchmarkComponent(
                    component_id="component_1",
                    target_symbol=target_symbol,
                    asset_class=str(payload.get("asset_class") or "").strip(),
                    theme_bucket=str(payload.get("theme_bucket") or "").strip(),
                    component_role=str(payload.get("component_role") or "primary").strip(),
                    start_date=start_date,
                    end_date=end_date,
                    weight=1.0,
                    market_condition_tags=_strings(payload.get("market_condition_tags") or ()),
                    data_availability_tags=_strings(payload.get("data_availability_tags") or ()),
                    target_context_ref=str(payload.get("target_context_ref") or "").strip(),
                    stress_exception_ref=str(payload.get("stress_exception_ref") or "").strip(),
                ),
            )
        return cls(
            contract_id=str(payload.get("contract_id") or "").strip(),
            target_symbol=target_symbol,
            start_date=start_date,
            end_date=end_date,
            benchmark_components=components,
            min_trading_days=min_trading_days,
            market_condition_tags=_strings(payload.get("market_condition_tags") or ()),
            data_snapshot_ref=str(payload.get("data_snapshot_ref") or "").strip(),
            cost_model_ref=str(payload.get("cost_model_ref") or "").strip(),
            baseline_refs=_strings(payload.get("baseline_refs") or ()),
            training_universe_symbols=tuple(symbol.upper() for symbol in _strings(payload.get("training_universe_symbols") or ())),
            excluded_training_windows=tuple(dict(window) for window in windows if isinstance(window, Mapping)),
            guardrail_refs=_strings(payload.get("guardrail_refs") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "target_symbol": self.target_symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "benchmark_components": [component.to_dict() for component in self.benchmark_components],
            "min_trading_days": self.min_trading_days,
            "market_condition_tags": list(self.market_condition_tags),
            "data_snapshot_ref": self.data_snapshot_ref,
            "cost_model_ref": self.cost_model_ref,
            "baseline_refs": list(self.baseline_refs),
            "training_universe_symbols": list(self.training_universe_symbols),
            "excluded_training_windows": list(self.excluded_training_windows),
            "guardrail_refs": list(self.guardrail_refs),
        }


@dataclass(frozen=True)
class BenchmarkValidation:
    """Validation result for a benchmark contract."""

    contract_type: str
    validation_status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    contract: BenchmarkContract | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "contract": self.contract.to_dict() if self.contract else None,
        }


def validate_benchmark_contract(payload: Mapping[str, Any]) -> BenchmarkValidation:
    """Validate the first-order benchmark contract rules."""

    errors: list[str] = []
    warnings: list[str] = []
    try:
        contract = BenchmarkContract.from_mapping(payload)
    except ValueError as exc:
        return BenchmarkValidation(
            contract_type="evaluation_benchmark_contract_validation",
            validation_status="failed",
            errors=(str(exc),),
            warnings=(),
            contract=None,
        )

    if not contract.contract_id:
        errors.append("contract_id is required")
    if not contract.target_symbol and not contract.benchmark_components:
        errors.append("target_symbol or benchmark_components is required")
    if contract.end_date <= contract.start_date:
        errors.append("end_date must be after start_date")
    if not contract.benchmark_components:
        errors.append("benchmark_components must include at least one component")
    component_ids = [component.component_id for component in contract.benchmark_components]
    if len(set(component_ids)) != len(component_ids):
        errors.append("benchmark component_id values must be unique")
    stress_weight = 0.0
    single_name_weight = 0.0
    etf_weight = 0.0
    crypto_weight = 0.0
    total_weight = 0.0
    for component in contract.benchmark_components:
        total_weight += component.weight
        if component.asset_class == "equity_single_name":
            single_name_weight += component.weight
        if component.asset_class == "equity_etf":
            etf_weight += component.weight
        if component.asset_class.startswith("crypto"):
            crypto_weight += component.weight
        if not component.component_id:
            errors.append("benchmark component_id is required")
        if not component.target_symbol:
            errors.append("benchmark component target_symbol is required")
        if not component.asset_class:
            errors.append(f"benchmark component {component.component_id} asset_class is required")
        if not component.theme_bucket:
            errors.append(f"benchmark component {component.component_id} theme_bucket is required")
        if not component.component_role:
            errors.append(f"benchmark component {component.component_id} component_role is required")
        elif component.component_role not in KNOWN_COMPONENT_ROLES:
            errors.append(f"benchmark component {component.component_id} component_role is not recognized")
        unknown_tags = set(component.data_availability_tags) - KNOWN_DATA_AVAILABILITY_TAGS
        if unknown_tags:
            errors.append(f"benchmark component {component.component_id} has unknown data_availability_tags: {', '.join(sorted(unknown_tags))}")
        critical_stress_tags = set(component.data_availability_tags) & CRITICAL_DATA_STRESS_TAGS
        if critical_stress_tags and component.component_role not in STRESS_COMPONENT_ROLES:
            errors.append(
                f"benchmark component {component.component_id} critical data stress tags require a stress component_role"
            )
        if component.component_role in STRESS_COMPONENT_ROLES:
            stress_weight += component.weight
            if not component.stress_exception_ref:
                errors.append(f"benchmark component {component.component_id} stress_exception_ref is required for stress components")
        if "missing_quote_order_book_context" in component.data_availability_tags and not component.asset_class.startswith("crypto"):
            errors.append(f"benchmark component {component.component_id} missing_quote_order_book_context is only accepted for crypto components")
        if _requires_target_context_review(component) and not component.target_context_ref and not _has_target_context_exception(component):
            errors.append(f"benchmark component {component.component_id} target_context_ref is required for non-ETF target routing")
        if component.end_date <= component.start_date:
            errors.append(f"benchmark component {component.component_id} end_date must be after start_date")
        if component.weight <= 0:
            errors.append(f"benchmark component {component.component_id} weight must be positive")
    if abs(total_weight - 1.0) > 0.000001:
        errors.append("benchmark component weights must sum to 1.0")
    if single_name_weight < MIN_SINGLE_NAME_COMPONENT_WEIGHT:
        errors.append("equity_single_name component weight must be at least 55% of the benchmark panel")
    if etf_weight > MAX_ETF_COMPONENT_WEIGHT:
        errors.append("equity_etf component weight must not exceed 30% of the benchmark panel")
    if crypto_weight > MAX_CRYPTO_COMPONENT_WEIGHT:
        errors.append("crypto component weight must not exceed 15% of the benchmark panel")
    if stress_weight > MAX_STRESS_COMPONENT_WEIGHT:
        errors.append("stress component weight must not exceed 15% of the benchmark panel")
    if contract.min_trading_days < 252:
        errors.append("min_trading_days must be at least one trading year")
    all_market_condition_tags = set(contract.market_condition_tags)
    for component in contract.benchmark_components:
        all_market_condition_tags.update(component.market_condition_tags)
    if len(all_market_condition_tags) < REQUIRED_MARKET_CONDITION_TAGS:
        errors.append("market_condition_tags must cover at least four distinct market conditions")
    if not contract.data_snapshot_ref:
        errors.append("data_snapshot_ref is required")
    if not contract.cost_model_ref:
        errors.append("cost_model_ref is required")
    if not contract.baseline_refs:
        errors.append("baseline_refs must include at least one accepted baseline")
    if not contract.excluded_training_windows:
        errors.append("excluded_training_windows is required for benchmark training-contamination exclusion")
    else:
        exclusion_errors = _validate_excluded_training_windows(contract.excluded_training_windows)
        errors.extend(exclusion_errors)
        for component in contract.benchmark_components:
            if not _component_window_is_excluded(component, contract.excluded_training_windows):
                errors.append(
                    "excluded_training_windows must cover every benchmark component target/window "
                    f"({component.component_id}:{component.target_symbol})"
                )
    if not contract.guardrail_refs:
        warnings.append("guardrail_refs is empty; primary benchmark remains valid but overfit detection is weaker")

    return BenchmarkValidation(
        contract_type="evaluation_benchmark_contract_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
        warnings=tuple(warnings),
        contract=contract,
    )


def is_training_fold_blocked_by_benchmark(
    contract: BenchmarkContract,
    *,
    target_symbol: str,
    fold_start_date: date | str,
    fold_end_date: date | str,
) -> bool:
    """Return true when a target fold overlaps a sealed benchmark component."""

    symbol = target_symbol.strip().upper()
    start = date.fromisoformat(fold_start_date) if isinstance(fold_start_date, str) else fold_start_date
    end = date.fromisoformat(fold_end_date) if isinstance(fold_end_date, str) else fold_end_date
    if end <= start:
        raise ValueError("fold_end_date must be after fold_start_date")
    return any(
        component.target_symbol == symbol and _windows_overlap(start, end, component.start_date, component.end_date)
        for component in contract.benchmark_components
    )


def _requires_target_context_review(component: BenchmarkComponent) -> bool:
    return component.asset_class in {"equity_single_name", "crypto_spot", "crypto_asset"}


def _has_target_context_exception(component: BenchmarkComponent) -> bool:
    return (
        component.component_role in STRESS_COMPONENT_ROLES
        and bool(component.stress_exception_ref)
        and bool(set(component.data_availability_tags) & TARGET_CONTEXT_EXCEPTION_TAGS)
    )


def _validate_excluded_training_windows(windows: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, window in enumerate(windows, start=1):
        try:
            start = _parse_date(window.get("start_date"), field_name="excluded_training_windows.start_date")
            end = _parse_date(window.get("end_date"), field_name="excluded_training_windows.end_date")
        except ValueError as exc:
            errors.append(f"excluded_training_windows[{index}] {exc}")
            continue
        if end <= start:
            errors.append(f"excluded_training_windows[{index}] end_date must be after start_date")
    return errors


def _component_window_is_excluded(component: BenchmarkComponent, windows: Sequence[Mapping[str, Any]]) -> bool:
    for window in windows:
        raw_symbol = str(window.get("target_symbol") or "").strip().upper()
        if raw_symbol and raw_symbol != component.target_symbol:
            continue
        try:
            start = _parse_date(window.get("start_date"), field_name="excluded_training_windows.start_date")
            end = _parse_date(window.get("end_date"), field_name="excluded_training_windows.end_date")
        except ValueError:
            continue
        if start <= component.start_date and end >= component.end_date:
            return True
    return False


def _windows_overlap(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start < right_end and right_start < left_end
