"""Validation rules for Upstream evidence substrate and x402 semantic rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


RECONCILIATION_MATCH_RATE_MIN = 0.99


@dataclass(frozen=True)
class RowSampleValidation:
    tx_count: int
    configured_sample_size: int
    actual_sample_size: int
    matched_count: int
    row_sample_match_rate: float
    validation_status: str
    gate_passed: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationLogRecord:
    validation_id: str
    run_timestamp: str
    run_id: str
    chain: str
    stablecoin: str
    validation_type: str
    source_a: str
    source_b: str
    window_start: str
    window_end: str
    bq_row_count: int
    rpc_row_count: int | None
    node_row_count: int | None
    sample_size: int
    matched_count: int
    match_rate: float
    row_sample_match_rate: float | None
    discrepancy_count: int
    source_count: int
    gate_passed: bool
    validation_status: str
    notes: str
    upstream_match_rate: float | None
    upstream_last_validated_at: str | None
    upstream_validation_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_row_sample_validation(
    *,
    tx_count: int,
    configured_sample_size: int,
    matched_count: int,
    threshold: float = RECONCILIATION_MATCH_RATE_MIN,
) -> RowSampleValidation:
    actual_sample_size = min(tx_count, configured_sample_size)
    if actual_sample_size <= 0:
        match_rate = 0.0
    else:
        match_rate = matched_count / actual_sample_size
    gate_passed = match_rate >= threshold and actual_sample_size > 0
    return RowSampleValidation(
        tx_count=tx_count,
        configured_sample_size=configured_sample_size,
        actual_sample_size=actual_sample_size,
        matched_count=matched_count,
        row_sample_match_rate=match_rate,
        validation_status="passed" if gate_passed else "failed",
        gate_passed=gate_passed,
    )


def derive_data_quality_status(
    *,
    upstream_match_rate: float | None,
    upstream_validation_status: str,
    row_sample_match_rate: float | None,
    freshness_within_threshold: bool,
    under_review: bool,
    threshold: float = RECONCILIATION_MATCH_RATE_MIN,
) -> str:
    if under_review:
        return "under_review"
    if upstream_validation_status == "stale" or not freshness_within_threshold:
        return "stale"
    if upstream_match_rate is None or upstream_match_rate < threshold:
        return "partially_validated"
    if row_sample_match_rate is None:
        return "partially_validated"
    if row_sample_match_rate < threshold:
        return "partially_validated"
    return "validated"


def build_row_sample_validation_log(
    *,
    run_id: str,
    run_timestamp: str,
    chain: str,
    stablecoin: str,
    window_start: str,
    window_end: str,
    tx_count: int,
    configured_sample_size: int,
    matched_count: int,
    upstream_match_rate: float | None,
    upstream_last_validated_at: str | None,
    upstream_validation_status: str,
    source_b: str = "rpc",
) -> ValidationLogRecord:
    sample = compute_row_sample_validation(
        tx_count=tx_count,
        configured_sample_size=configured_sample_size,
        matched_count=matched_count,
    )
    source_count = 2 if source_b == "rpc" else 1
    validation_id = f"{run_id}_{chain}_{stablecoin}_row_sample"
    return ValidationLogRecord(
        validation_id=validation_id,
        run_timestamp=run_timestamp,
        run_id=run_id,
        chain=chain,
        stablecoin=stablecoin,
        validation_type="row_sample",
        source_a="bigquery",
        source_b=source_b,
        window_start=window_start,
        window_end=window_end,
        bq_row_count=tx_count,
        rpc_row_count=None,
        node_row_count=None,
        sample_size=sample.actual_sample_size,
        matched_count=matched_count,
        match_rate=sample.row_sample_match_rate,
        row_sample_match_rate=sample.row_sample_match_rate,
        discrepancy_count=max(sample.actual_sample_size - matched_count, 0),
        source_count=source_count,
        gate_passed=sample.gate_passed and source_b != "own_node",
        validation_status=sample.validation_status if source_b != "own_node" else "partial",
        notes="Upstream evidence provenance included; own_node alone is never launch-validated."
        if source_b == "own_node"
        else "Upstream evidence provenance included.",
        upstream_match_rate=upstream_match_rate,
        upstream_last_validated_at=upstream_last_validated_at,
        upstream_validation_status=upstream_validation_status,
    )
