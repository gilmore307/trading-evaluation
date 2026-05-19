"""Benchmark contract validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

REQUIRED_MARKET_CONDITION_TAGS = 4


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
class BenchmarkContract:
    """Frozen primary benchmark contract."""

    contract_id: str
    target_symbol: str
    start_date: date
    end_date: date
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
        return cls(
            contract_id=str(payload.get("contract_id") or "").strip(),
            target_symbol=str(payload.get("target_symbol") or "").strip().upper(),
            start_date=_parse_date(payload.get("start_date"), field_name="start_date"),
            end_date=_parse_date(payload.get("end_date"), field_name="end_date"),
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
    if not contract.target_symbol:
        errors.append("target_symbol is required")
    if contract.end_date <= contract.start_date:
        errors.append("end_date must be after start_date")
    if contract.min_trading_days < 252:
        errors.append("min_trading_days must be at least one trading year")
    if len(set(contract.market_condition_tags)) < REQUIRED_MARKET_CONDITION_TAGS:
        errors.append("market_condition_tags must cover at least four distinct market conditions")
    if not contract.data_snapshot_ref:
        errors.append("data_snapshot_ref is required")
    if not contract.cost_model_ref:
        errors.append("cost_model_ref is required")
    if not contract.baseline_refs:
        errors.append("baseline_refs must include at least one accepted baseline")
    if contract.target_symbol and contract.target_symbol in set(contract.training_universe_symbols):
        errors.append("target_symbol must not appear in training_universe_symbols")
    if not contract.excluded_training_windows:
        warnings.append("excluded_training_windows is empty; provide explicit split exclusion evidence before acceptance")
    if not contract.guardrail_refs:
        warnings.append("guardrail_refs is empty; primary benchmark remains valid but overfit detection is weaker")

    return BenchmarkValidation(
        contract_type="evaluation_benchmark_contract_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
        warnings=tuple(warnings),
        contract=contract,
    )

