"""Deterministic rolling route metric helpers."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from pipeline.validate.validation import RECONCILIATION_MATCH_RATE_MIN


SHORT_WINDOW_LABELS = ("15m", "1h")
LONG_WINDOW_LABELS = ("24h", "7d")


@dataclass(frozen=True)
class ValidationProvenance:
    source_count: int
    row_sample_match_rate: float | None
    last_validated_at: str | None
    validation_type: str | None
    data_quality_status: str


@dataclass(frozen=True)
class RollingRouteMetric:
    metric_id: str
    cache_generation_timestamp: str
    metrics_timestamp: str
    window_label: str
    window_start: str
    window_end: str
    chain: str
    stablecoin: str
    route_id: str
    observed_cost_pct: float | None
    route_volume_usd: float
    total_observed_volume_usd: float
    route_share_pct: float | None
    tx_count: int
    source_count: int
    row_sample_match_rate: float | None
    last_validated_at: str | None
    data_quality_status: str
    data_quality_issue_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_metric_id(
    *,
    chain: str,
    stablecoin: str,
    route_id: str,
    window_label: str,
    window_start: str,
) -> str:
    key = f"{chain}|{stablecoin}|{route_id}|{window_label}|{window_start}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def windows_for_cadence(cadence: str) -> tuple[str, ...]:
    if cadence == "short":
        return SHORT_WINDOW_LABELS
    if cadence == "long":
        return LONG_WINDOW_LABELS
    raise ValueError(f"unsupported metrics cadence: {cadence}")


def build_route_metric(
    *,
    rows: list[dict[str, Any]],
    validation: ValidationProvenance | None,
    cache_generation_timestamp: str,
    metrics_timestamp: str,
    window_label: str,
    window_start: str,
    window_end: str,
    chain: str,
    stablecoin: str,
    route_id: str,
    total_observed_volume_usd: float,
) -> RollingRouteMetric:
    valid_amount_rows = [row for row in rows if row.get("amount_usd") is not None]
    data_quality_issue_count = len(rows) - len(valid_amount_rows)
    route_volume_usd = sum(float(row["amount_usd"]) for row in valid_amount_rows)
    total_fee_usd = sum(float(row.get("total_observed_fee_usd") or 0.0) for row in valid_amount_rows)
    observed_cost_pct = total_fee_usd / route_volume_usd if route_volume_usd else None
    route_share_pct = route_volume_usd / total_observed_volume_usd if total_observed_volume_usd else None

    provenance = validation or ValidationProvenance(
        source_count=0,
        row_sample_match_rate=None,
        last_validated_at=None,
        validation_type=None,
        data_quality_status="partially_validated",
    )
    quality_status = _downgrade_quality_for_issues(provenance.data_quality_status, data_quality_issue_count)

    return RollingRouteMetric(
        metric_id=compute_metric_id(
            chain=chain,
            stablecoin=stablecoin,
            route_id=route_id,
            window_label=window_label,
            window_start=window_start,
        ),
        cache_generation_timestamp=cache_generation_timestamp,
        metrics_timestamp=metrics_timestamp,
        window_label=window_label,
        window_start=window_start,
        window_end=window_end,
        chain=chain,
        stablecoin=stablecoin,
        route_id=route_id,
        observed_cost_pct=observed_cost_pct,
        route_volume_usd=route_volume_usd,
        total_observed_volume_usd=total_observed_volume_usd,
        route_share_pct=route_share_pct,
        tx_count=len(rows),
        source_count=provenance.source_count,
        row_sample_match_rate=provenance.row_sample_match_rate,
        last_validated_at=provenance.last_validated_at,
        data_quality_status=quality_status,
        data_quality_issue_count=data_quality_issue_count,
    )


def validation_quality_status(
    *,
    source_count: int,
    row_sample_match_rate: float | None,
    validation_stale: bool,
    under_review: bool = False,
) -> str:
    if under_review:
        return "under_review"
    if validation_stale:
        return "stale"
    if source_count >= 3 and row_sample_match_rate is not None and row_sample_match_rate >= RECONCILIATION_MATCH_RATE_MIN:
        return "validated"
    if source_count >= 2:
        return "partially_validated"
    return "partially_validated"


def _downgrade_quality_for_issues(status: str, data_quality_issue_count: int) -> str:
    if data_quality_issue_count <= 0:
        return status
    if status == "validated":
        return "partially_validated"
    return status
