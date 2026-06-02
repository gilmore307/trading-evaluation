"""Promotion replay contract validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

EXPECTED_REPLAY_MODE = "candidate_policy_replay"
EXPECTED_REPLAY_ROUTE_REF = "trading-execution://execution_runtime_component_graph/replay"
CANONICAL_REPLAY_START_DATE = date(2021, 1, 1)
CANONICAL_REPLAY_END_DATE = date(2026, 1, 1)
CANONICAL_REPLAY_EXPECTED_TRADING_DAYS = 1255
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
class ReplayContract:
    """Frozen candidate-policy replay contract."""

    contract_id: str
    replay_mode: str
    candidate_fold_id: str
    tradable_universe_policy_ref: str
    tradable_universe_ref: str
    start_date: date
    end_date: date
    min_trading_days: int
    market_condition_tags: tuple[str, ...]
    candidate_policy_ref: str
    replay_route_ref: str
    data_snapshot_ref: str
    cost_model_ref: str
    baseline_refs: tuple[str, ...]
    guardrail_refs: tuple[str, ...]
    selection_metric_refs: tuple[str, ...]
    excluded_training_windows: tuple[dict[str, Any], ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ReplayContract":
        try:
            min_trading_days = int(payload.get("min_trading_days", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("min_trading_days must be an integer") from exc
        windows = payload.get("excluded_training_windows") or []
        if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)):
            windows = []
        return cls(
            contract_id=str(payload.get("contract_id") or "").strip(),
            replay_mode=str(payload.get("replay_mode") or "").strip(),
            candidate_fold_id=str(payload.get("candidate_fold_id") or payload.get("fold_id") or "").strip(),
            tradable_universe_policy_ref=str(payload.get("tradable_universe_policy_ref") or "").strip(),
            tradable_universe_ref=str(payload.get("tradable_universe_ref") or "").strip(),
            start_date=_parse_date(payload.get("start_date"), field_name="start_date"),
            end_date=_parse_date(payload.get("end_date"), field_name="end_date"),
            min_trading_days=min_trading_days,
            market_condition_tags=_strings(payload.get("market_condition_tags") or ()),
            candidate_policy_ref=str(payload.get("candidate_policy_ref") or "").strip(),
            replay_route_ref=str(payload.get("replay_route_ref") or "").strip(),
            data_snapshot_ref=str(payload.get("data_snapshot_ref") or "").strip(),
            cost_model_ref=str(payload.get("cost_model_ref") or "").strip(),
            baseline_refs=_strings(payload.get("baseline_refs") or ()),
            guardrail_refs=_strings(payload.get("guardrail_refs") or ()),
            selection_metric_refs=_strings(payload.get("selection_metric_refs") or ()),
            excluded_training_windows=tuple(dict(window) for window in windows if isinstance(window, Mapping)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "replay_mode": self.replay_mode,
            "candidate_fold_id": self.candidate_fold_id,
            "tradable_universe_policy_ref": self.tradable_universe_policy_ref,
            "tradable_universe_ref": self.tradable_universe_ref,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "min_trading_days": self.min_trading_days,
            "market_condition_tags": list(self.market_condition_tags),
            "candidate_policy_ref": self.candidate_policy_ref,
            "replay_route_ref": self.replay_route_ref,
            "data_snapshot_ref": self.data_snapshot_ref,
            "cost_model_ref": self.cost_model_ref,
            "baseline_refs": list(self.baseline_refs),
            "guardrail_refs": list(self.guardrail_refs),
            "selection_metric_refs": list(self.selection_metric_refs),
            "excluded_training_windows": list(self.excluded_training_windows),
        }


@dataclass(frozen=True)
class ReplayValidation:
    """Validation result for a replay contract."""

    contract_type: str
    validation_status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    contract: ReplayContract | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "contract": self.contract.to_dict() if self.contract else None,
        }


def validate_replay_contract(payload: Mapping[str, Any]) -> ReplayValidation:
    """Validate the accepted candidate-policy replay rules."""

    errors: list[str] = []
    warnings: list[str] = []
    try:
        contract = ReplayContract.from_mapping(payload)
    except ValueError as exc:
        return ReplayValidation(
            contract_type="evaluation_replay_contract_validation",
            validation_status="failed",
            errors=(str(exc),),
            warnings=(),
            contract=None,
        )

    if payload.get("target_symbol"):
        errors.append("target_symbol is not allowed for promotion replay; use candidate_fold_id")
    if payload.get("target_refs") or payload.get("replay_target_refs") or payload.get("candidate_target_refs"):
        errors.append("target_refs are not allowed for promotion replay; use tradable_universe_ref")
    if payload.get("replay_components"):
        errors.append("replay_components are obsolete for promotion replay; use candidate_policy_ref")
    if not contract.contract_id:
        errors.append("contract_id is required")
    if contract.replay_mode != EXPECTED_REPLAY_MODE:
        errors.append(f"replay_mode must be {EXPECTED_REPLAY_MODE}")
    if contract.end_date <= contract.start_date:
        errors.append("end_date must be after start_date")
    if contract.start_date == CANONICAL_REPLAY_START_DATE and contract.end_date == CANONICAL_REPLAY_END_DATE:
        if contract.min_trading_days < CANONICAL_REPLAY_EXPECTED_TRADING_DAYS:
            errors.append("min_trading_days must be at least 1255 for the canonical replay window")
    elif contract.min_trading_days <= 0:
        errors.append("min_trading_days must be positive for a fold-bound replay window")
    if len(set(contract.market_condition_tags)) < REQUIRED_MARKET_CONDITION_TAGS:
        errors.append("market_condition_tags must cover at least four distinct market conditions")
    if not contract.candidate_policy_ref:
        errors.append("candidate_policy_ref is required")
    if not contract.candidate_fold_id:
        errors.append("candidate_fold_id is required")
    if not contract.tradable_universe_policy_ref:
        errors.append("tradable_universe_policy_ref is required")
    if not contract.tradable_universe_ref:
        errors.append("tradable_universe_ref is required")
    if not contract.replay_route_ref:
        errors.append("replay_route_ref is required")
    elif contract.replay_route_ref != EXPECTED_REPLAY_ROUTE_REF:
        errors.append(f"replay_route_ref must be {EXPECTED_REPLAY_ROUTE_REF}")
    if not contract.data_snapshot_ref:
        errors.append("data_snapshot_ref is required")
    if not contract.cost_model_ref:
        errors.append("cost_model_ref is required")
    if not contract.baseline_refs:
        errors.append("baseline_refs must include at least one accepted baseline")
    if not contract.selection_metric_refs:
        errors.append("selection_metric_refs must include at least one accepted performance metric")
    if not contract.excluded_training_windows:
        errors.append("excluded_training_windows is required for replay training-contamination exclusion")
    else:
        errors.extend(_validate_excluded_training_windows(contract.excluded_training_windows))
        if not _replay_window_is_excluded(contract, contract.excluded_training_windows):
            errors.append("excluded_training_windows must cover the full replay window")
    if not contract.guardrail_refs:
        errors.append("guardrail_refs must include at least one accepted guardrail replay")

    return ReplayValidation(
        contract_type="evaluation_replay_contract_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
        warnings=tuple(warnings),
        contract=contract,
    )


def is_training_fold_blocked_by_replay(
    contract: ReplayContract,
    *,
    fold_start_date: date | str,
    fold_end_date: date | str,
) -> bool:
    """Return true when a fold overlaps the sealed candidate-policy replay window."""

    start = date.fromisoformat(fold_start_date) if isinstance(fold_start_date, str) else fold_start_date
    end = date.fromisoformat(fold_end_date) if isinstance(fold_end_date, str) else fold_end_date
    if end <= start:
        raise ValueError("fold_end_date must be after fold_start_date")
    return _windows_overlap(start, end, contract.start_date, contract.end_date)


def _validate_excluded_training_windows(windows: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, window in enumerate(windows, start=1):
        if window.get("target_symbol"):
            errors.append(f"excluded_training_windows[{index}] target_symbol is not allowed; replay exclusion must be global")
        try:
            start = _parse_date(window.get("start_date"), field_name="excluded_training_windows.start_date")
            end = _parse_date(window.get("end_date"), field_name="excluded_training_windows.end_date")
        except ValueError as exc:
            errors.append(f"excluded_training_windows[{index}] {exc}")
            continue
        if end <= start:
            errors.append(f"excluded_training_windows[{index}] end_date must be after start_date")
    return errors


def _replay_window_is_excluded(contract: ReplayContract, windows: Sequence[Mapping[str, Any]]) -> bool:
    for window in windows:
        try:
            start = _parse_date(window.get("start_date"), field_name="excluded_training_windows.start_date")
            end = _parse_date(window.get("end_date"), field_name="excluded_training_windows.end_date")
        except ValueError:
            continue
        if start <= contract.start_date and end >= contract.end_date:
            return True
    return False


def _windows_overlap(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start < right_end and right_start < left_end
