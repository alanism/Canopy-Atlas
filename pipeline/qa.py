"""Phase 12 QA and audit helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AUDIT_REQUIRED_FIELDS = (
    "amount_usd",
    "amount_tokens",
    "block_number",
    "block_timestamp",
    "chain",
    "from_address",
    "route_id",
    "token_symbol",
    "to_address",
    "total_observed_fee_usd",
)


@dataclass(frozen=True)
class AuditResult:
    passed: bool
    missing_fields: tuple[str, ...]
    notes: str


def audit_normalized_transaction(row: dict[str, Any]) -> AuditResult:
    missing = tuple(field for field in AUDIT_REQUIRED_FIELDS if row.get(field) in (None, ""))
    if missing:
        return AuditResult(False, missing, "normalized transaction row is missing required audit fields")
    if row.get("self_transfer_flag") is True:
        return AuditResult(False, (), "self-transfer row must not be promoted into public metrics")
    return AuditResult(True, (), "normalized transaction row passes required audit fields")


def observed_cost_pct(rows: list[dict[str, Any]]) -> float | None:
    amount = sum(float(row.get("amount_usd") or 0) for row in rows)
    if amount == 0:
        return None
    fees = sum(float(row.get("total_observed_fee_usd") or 0) for row in rows)
    return fees / amount


def integration_readiness(
    *,
    upstream_status: str,
    public_api_status: str,
    product_claims_safe: bool,
    cache_failure_verified: bool,
    health_down_verified: bool,
) -> dict[str, str]:
    upstream = "Green" if upstream_status == "validated" else "Yellow"
    public_api = "sample mode" if public_api_status == "sample_bootstrap" else public_api_status
    product_claims = "safe" if product_claims_safe else "needs fallback copy"
    qa_status = "ready_for_sample_mode" if cache_failure_verified and health_down_verified else "blocked_for_public_launch"
    return {
        "upstream": upstream,
        "decision_layer": "compatible",
        "public_api": public_api,
        "product_claims": product_claims,
        "qa_status": qa_status,
    }
