"""Fold settlement metric assembly for promotion evaluation.

The helper consumes replay decision rows from an accepted replay run and
emits deterministic metric evidence. It does not run models, call providers,
write active model pointers, construct orders, or mutate accounts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

FOLD_SETTLEMENT_RUN_CONTRACT = "fold_settlement_run"
FOLD_SETTLEMENT_METRIC_CONTRACT = "fold_settlement_metric"
DEFAULT_MIN_DECISION_ROWS = 20
DEFAULT_MIN_AUROC = 0.53


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _float(row: Mapping[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = row.get(name)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return default


def _label(row: Mapping[str, Any]) -> int | None:
    value = row.get("outcome_label", row.get("label", row.get("realized_label")))
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in {"1", "true", "positive", "win", "profitable", "up", "success"}:
        return 1
    if text in {"0", "false", "negative", "loss", "unprofitable", "down", "failure"}:
        return 0
    realized = _float(row, "realized_return", "net_return", "candidate_return", default=float("nan"))
    if math.isfinite(realized):
        return 1 if realized > 0 else 0
    return None


def _score(row: Mapping[str, Any]) -> float | None:
    for name in ("prediction_score", "predicted_score", "probability", "confidence_score", "alpha_score", "rank_score"):
        value = row.get(name)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def _auroc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    pairs = [(score, label) for label, score in zip(labels, scores, strict=True)]
    positives = sum(1 for _score_value, label in pairs if label == 1)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        return None
    pairs.sort(key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += average_rank * sum(1 for _score_value, label in pairs[index:end] if label == 1)
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _max_drawdown(cumulative_returns: Sequence[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in cumulative_returns:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _feature_columns(rows: Sequence[Mapping[str, Any]], requested: Iterable[str] | None) -> tuple[str, ...]:
    if requested:
        return tuple(str(name) for name in requested if str(name).strip())
    names: list[str] = []
    for row in rows:
        for key, value in row.items():
            if not str(key).startswith("feature_"):
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            if key not in names:
                names.append(str(key))
    return tuple(names)


def _feature_matrix(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> list[list[float]]:
    matrix: list[list[float]] = []
    for row in rows:
        values: list[float] = []
        valid = True
        for column in columns:
            try:
                value = float(row.get(column))
            except (TypeError, ValueError):
                valid = False
                break
            if not math.isfinite(value):
                valid = False
                break
            values.append(value)
        if valid:
            matrix.append(values)
    return matrix


def _center(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    if not matrix:
        return []
    columns = len(matrix[0])
    means = [sum(row[index] for row in matrix) / len(matrix) for index in range(columns)]
    return [[value - means[index] for index, value in enumerate(row)] for row in matrix]


def _covariance(centered: Sequence[Sequence[float]]) -> list[list[float]]:
    if len(centered) < 2:
        return []
    columns = len(centered[0])
    denom = float(len(centered) - 1)
    return [
        [sum(row[i] * row[j] for row in centered) / denom for j in range(columns)]
        for i in range(columns)
    ]


def _mat_vec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    return [sum(value * vector[index] for index, value in enumerate(row)) for row in matrix]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _top_eigenvalues(matrix: Sequence[Sequence[float]], count: int = 2) -> list[float]:
    if not matrix:
        return []
    working = [list(row) for row in matrix]
    size = len(working)
    values: list[float] = []
    for _ in range(min(count, size)):
        vector = [1.0 / math.sqrt(size)] * size
        for _iteration in range(50):
            next_vector = _mat_vec(working, vector)
            norm = math.sqrt(_dot(next_vector, next_vector))
            if norm <= 1e-12:
                break
            vector = [value / norm for value in next_vector]
        eigenvalue = _dot(vector, _mat_vec(working, vector))
        if eigenvalue <= 1e-12:
            break
        values.append(eigenvalue)
        for i in range(size):
            for j in range(size):
                working[i][j] -= eigenvalue * vector[i] * vector[j]
    return values


def _structure_metrics(rows: Sequence[Mapping[str, Any]], feature_columns: Iterable[str] | None) -> dict[str, Any]:
    columns = _feature_columns(rows, feature_columns)
    matrix = _feature_matrix(rows, columns)
    if len(matrix) < 3 or len(columns) < 2:
        return {
            "feature_column_count": len(columns),
            "feature_row_count": len(matrix),
            "pca_available": False,
            "pcoa_available": False,
        }
    centered = _center(matrix)
    covariance = _covariance(centered)
    eigenvalues = _top_eigenvalues(covariance, count=2)
    total_variance = sum(max(row[index], 0.0) for index, row in enumerate(covariance))
    top_variance_ratio = sum(eigenvalues) / total_variance if total_variance > 0 else None
    pairwise_distances: list[float] = []
    for i, left in enumerate(centered):
        for right in centered[i + 1 :]:
            pairwise_distances.append(math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True))))
    return {
        "feature_column_count": len(columns),
        "feature_row_count": len(matrix),
        "feature_columns": list(columns),
        "pca_available": True,
        "pca_top2_variance_ratio": top_variance_ratio,
        "pca_top_eigenvalues": eigenvalues,
        "pcoa_available": True,
        "pcoa_mean_pairwise_distance": sum(pairwise_distances) / len(pairwise_distances) if pairwise_distances else None,
        "pcoa_pairwise_distance_count": len(pairwise_distances),
    }


@dataclass(frozen=True)
class SettlementValidation:
    """Validation result for a fold settlement run."""

    contract_type: str
    validation_status: str
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
        }


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_nonnegative_int(metrics: Mapping[str, Any], field: str, errors: list[str]) -> None:
    value = metrics.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"metrics.{field} must be a non-negative integer")


def _validate_finite_number(metrics: Mapping[str, Any], field: str, errors: list[str]) -> None:
    if not _is_finite_number(metrics.get(field)):
        errors.append(f"metrics.{field} must be a finite number")


def _validate_optional_probability(metrics: Mapping[str, Any], field: str, errors: list[str]) -> None:
    value = metrics.get(field)
    if value is None:
        return
    if not _is_finite_number(value) or not 0.0 <= float(value) <= 1.0:
        errors.append(f"metrics.{field} must be null or a finite number between 0 and 1")


def _validate_optional_nonnegative_number(metrics: Mapping[str, Any], field: str, errors: list[str]) -> None:
    value = metrics.get(field)
    if value is None:
        return
    if not _is_finite_number(value) or float(value) < 0.0:
        errors.append(f"metrics.{field} must be null or a non-negative finite number")


def build_fold_settlement_run(
    *,
    fold_id: str,
    candidate_model_ref: str,
    benchmark_contract_ref: str,
    replay_result_ref: str,
    decision_rows: Sequence[Mapping[str, Any]],
    baseline_ref: str | None = None,
    feature_columns: Iterable[str] | None = None,
    min_decision_rows: int = DEFAULT_MIN_DECISION_ROWS,
    min_auroc: float = DEFAULT_MIN_AUROC,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build deterministic fold-settlement metrics from replay decision rows."""

    rows = [dict(row) for row in decision_rows]
    realized_returns = [_float(row, "net_return", "realized_return", "candidate_return") for row in rows]
    baseline_returns = [_float(row, "baseline_return", "benchmark_return", "incumbent_return") for row in rows]
    costs = [_float(row, "cost", "trading_cost", "cost_drag") for row in rows]
    net_returns = [value - cost for value, cost in zip(realized_returns, costs, strict=True)]
    cumulative: list[float] = []
    running = 0.0
    for value in net_returns:
        running += value
        cumulative.append(running)
    labels_and_scores = [(_label(row), _score(row)) for row in rows]
    labels = [int(label) for label, score in labels_and_scores if label is not None and score is not None]
    scores = [float(score) for label, score in labels_and_scores if label is not None and score is not None]
    auroc = _auroc(labels, scores) if labels and scores else None
    wins = [value for value in net_returns if value > 0]
    losses = [value for value in net_returns if value <= 0]
    structure = _structure_metrics(rows, feature_columns)
    net_return_total = sum(net_returns)
    baseline_return_total = sum(baseline_returns)
    gate_failures: list[str] = []
    if len(rows) < min_decision_rows:
        gate_failures.append("decision_row_count_below_minimum")
    if net_return_total <= baseline_return_total:
        gate_failures.append("net_return_not_above_baseline")
    if auroc is None:
        gate_failures.append("auroc_unavailable")
    elif auroc < min_auroc:
        gate_failures.append("auroc_below_minimum")
    decision_status = "passed" if not gate_failures else "review_required"
    settlement_id = _stable_id("settlement", fold_id, candidate_model_ref, benchmark_contract_ref, replay_result_ref)
    metrics = {
        "contract_type": FOLD_SETTLEMENT_METRIC_CONTRACT,
        "settlement_run_ref": settlement_id,
        "decision_row_count": len(rows),
        "net_return_total": net_return_total,
        "baseline_return_total": baseline_return_total,
        "excess_return_total": net_return_total - baseline_return_total,
        "max_drawdown": _max_drawdown(cumulative),
        "turnover_proxy_count": sum(1 for row in rows if str(row.get("action") or row.get("decision") or "").lower() not in {"", "hold", "skip", "no_trade"}),
        "hit_rate": len(wins) / len(net_returns) if net_returns else None,
        "payoff_ratio": (sum(wins) / len(wins)) / abs(sum(losses) / len(losses)) if wins and losses else None,
        "auroc": auroc,
        "auroc_pair_count": len(labels),
        "brier_score": (
            sum((score - label) ** 2 for label, score in zip(labels, scores, strict=True)) / len(labels)
            if labels
            else None
        ),
        **structure,
    }
    run = {
        "contract_type": FOLD_SETTLEMENT_RUN_CONTRACT,
        "fold_settlement_run_id": settlement_id,
        "fold_id": fold_id,
        "candidate_model_ref": candidate_model_ref,
        "benchmark_contract_ref": benchmark_contract_ref,
        "replay_result_ref": replay_result_ref,
        "baseline_ref": baseline_ref,
        "created_at_utc": created_at_utc or _now_utc(),
        "decision_status": decision_status,
        "gate_failures": gate_failures,
        "metric_refs": [f"{settlement_id}:metrics"],
        "metrics": metrics,
        "agent_review_required": True,
        "agent_review_scope": "promotion-evaluation-review",
        "model_activation_performed": False,
        "active_model_config_written": False,
        "broker_execution_performed": False,
        "account_mutation_performed": False,
    }
    validation = validate_fold_settlement_run(run)
    if validation.validation_status != "passed":
        raise ValueError("; ".join(validation.errors))
    return run


def validate_fold_settlement_run(payload: Mapping[str, Any]) -> SettlementValidation:
    errors: list[str] = []
    required = (
        "contract_type",
        "fold_settlement_run_id",
        "fold_id",
        "candidate_model_ref",
        "benchmark_contract_ref",
        "replay_result_ref",
        "created_at_utc",
        "decision_status",
        "gate_failures",
        "metric_refs",
        "metrics",
        "agent_review_required",
        "agent_review_scope",
    )
    for field in required:
        if payload.get(field) in (None, ""):
            errors.append(f"{field} is required")
    if payload.get("contract_type") != FOLD_SETTLEMENT_RUN_CONTRACT:
        errors.append(f"contract_type must be {FOLD_SETTLEMENT_RUN_CONTRACT}")
    if payload.get("decision_status") not in {"passed", "review_required", "failed"}:
        errors.append("decision_status is not accepted")
    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        errors.append("metrics must be an object")
    elif metrics.get("contract_type") != FOLD_SETTLEMENT_METRIC_CONTRACT:
        errors.append(f"metrics.contract_type must be {FOLD_SETTLEMENT_METRIC_CONTRACT}")
    elif isinstance(metrics, Mapping):
        _validate_settlement_metrics(payload, metrics, errors)
    gate_failures = payload.get("gate_failures")
    if not isinstance(gate_failures, list):
        errors.append("gate_failures must be a list")
    elif payload.get("decision_status") == "passed" and gate_failures:
        errors.append("passed settlement runs must not include gate_failures")
    elif payload.get("decision_status") in {"review_required", "failed"} and not gate_failures:
        errors.append("non-passed settlement runs must include at least one gate_failure")
    metric_refs = payload.get("metric_refs")
    settlement_id = str(payload.get("fold_settlement_run_id") or "")
    expected_metric_ref = f"{settlement_id}:metrics" if settlement_id else ""
    if not isinstance(metric_refs, list) or not all(isinstance(item, str) and item for item in metric_refs):
        errors.append("metric_refs must be a non-empty string list")
    elif expected_metric_ref and expected_metric_ref not in metric_refs:
        errors.append("metric_refs must include the settlement metrics ref")
    if payload.get("agent_review_required") is not True:
        errors.append("agent_review_required must be true")
    if payload.get("agent_review_scope") != "promotion-evaluation-review":
        errors.append("agent_review_scope must be promotion-evaluation-review")
    for field in ("model_activation_performed", "active_model_config_written", "broker_execution_performed", "account_mutation_performed"):
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    return SettlementValidation(
        contract_type="fold_settlement_run_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
    )


def _validate_settlement_metrics(payload: Mapping[str, Any], metrics: Mapping[str, Any], errors: list[str]) -> None:
    required_metric_fields = (
        "settlement_run_ref",
        "decision_row_count",
        "net_return_total",
        "baseline_return_total",
        "excess_return_total",
        "max_drawdown",
        "turnover_proxy_count",
        "hit_rate",
        "payoff_ratio",
        "auroc",
        "auroc_pair_count",
        "brier_score",
        "feature_column_count",
        "feature_row_count",
        "pca_available",
        "pcoa_available",
    )
    for field in required_metric_fields:
        if field not in metrics:
            errors.append(f"metrics.{field} is required")
    settlement_id = str(payload.get("fold_settlement_run_id") or "")
    if settlement_id and metrics.get("settlement_run_ref") != settlement_id:
        errors.append("metrics.settlement_run_ref must match fold_settlement_run_id")
    for field in ("decision_row_count", "turnover_proxy_count", "auroc_pair_count", "feature_column_count", "feature_row_count"):
        if metrics.get(field) is not None:
            _validate_nonnegative_int(metrics, field, errors)
    for field in ("net_return_total", "baseline_return_total", "excess_return_total", "max_drawdown"):
        if metrics.get(field) is not None:
            _validate_finite_number(metrics, field, errors)
    for field in ("hit_rate", "auroc", "brier_score", "pca_top2_variance_ratio"):
        _validate_optional_probability(metrics, field, errors)
    for field in ("payoff_ratio", "pcoa_mean_pairwise_distance"):
        _validate_optional_nonnegative_number(metrics, field, errors)
    for field in ("pca_available", "pcoa_available"):
        value = metrics.get(field)
        if value is not None and not isinstance(value, bool):
            errors.append(f"metrics.{field} must be a boolean")
    if all(_is_finite_number(metrics.get(field)) for field in ("net_return_total", "baseline_return_total", "excess_return_total")):
        expected_excess = float(metrics["net_return_total"]) - float(metrics["baseline_return_total"])
        if not math.isclose(float(metrics["excess_return_total"]), expected_excess, rel_tol=1e-9, abs_tol=1e-12):
            errors.append("metrics.excess_return_total must equal net_return_total - baseline_return_total")
    gate_failures = payload.get("gate_failures")
    if isinstance(gate_failures, list):
        decision_rows = metrics.get("decision_row_count")
        auroc = metrics.get("auroc")
        net_return = metrics.get("net_return_total")
        baseline_return = metrics.get("baseline_return_total")
        if isinstance(decision_rows, int) and not isinstance(decision_rows, bool) and decision_rows < DEFAULT_MIN_DECISION_ROWS:
            if "decision_row_count_below_minimum" not in gate_failures:
                errors.append("gate_failures must include decision_row_count_below_minimum")
        if auroc is None:
            if "auroc_unavailable" not in gate_failures:
                errors.append("gate_failures must include auroc_unavailable when metrics.auroc is null")
        elif _is_finite_number(auroc) and float(auroc) < DEFAULT_MIN_AUROC and "auroc_below_minimum" not in gate_failures:
            errors.append("gate_failures must include auroc_below_minimum")
        if _is_finite_number(net_return) and _is_finite_number(baseline_return) and float(net_return) <= float(baseline_return):
            if "net_return_not_above_baseline" not in gate_failures:
                errors.append("gate_failures must include net_return_not_above_baseline")


def load_decision_rows(path: Path) -> list[dict[str, Any]]:
    """Load replay decision rows from JSON, JSONL, or CSV."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    text = path.read_text(encoding="utf-8")
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        rows = payload.get("decisions") or payload.get("rows") or payload.get("decision_rows")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    raise ValueError("decision rows must be a JSON list, JSON object with decisions/rows, JSONL, or CSV")


__all__ = [
    "FOLD_SETTLEMENT_METRIC_CONTRACT",
    "FOLD_SETTLEMENT_RUN_CONTRACT",
    "SettlementValidation",
    "build_fold_settlement_run",
    "load_decision_rows",
    "validate_fold_settlement_run",
]
