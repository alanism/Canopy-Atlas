"""Generic upstream contract gate helpers for public Canopy Atlas builds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


QueryRunner = Callable[[str, dict[str, Any]], list[dict[str, Any]]]

TOKEN_ALLOWLIST_SQL = """
SELECT chain, token_symbol, canonical_symbol, is_active, notes
FROM `{project}.{dataset}.token_symbol_contract_v1`
WHERE chain = @chain
  AND token_symbol = @token_symbol
  AND is_active = TRUE
"""

SIGNAL_AVAILABILITY_SQL = """
SELECT
  x402_signal_source_available,
  rpc_pointer_available,
  memo_field_available,
  program_id_available,
  raw_instruction_ref_available,
  evaluated_at,
  notes
FROM `{project}.{dataset}.x402_signal_availability_v1`
"""

FRESHNESS_SQL = """
SELECT
  token_symbol,
  chain,
  freshness_hours,
  health_state,
  latest_block_timestamp,
  global_max_freshness_hours
FROM `{project}.{dataset}.upstream_freshness_summary_v1`
WHERE token_symbol = @token_symbol
  AND chain = @chain
"""

RECONCILIATION_SQL = """
SELECT
  token_symbol,
  chain,
  run_timestamp,
  source_row_count,
  verifier_row_count,
  match_rate,
  discrepancy_count,
  gate_passed
FROM `{project}.{dataset}.upstream_reconciliation_latest_v1`
WHERE token_symbol = @token_symbol
  AND chain = @chain
"""


@dataclass(frozen=True)
class SignalAvailability:
    x402_signal_source_available: bool
    rpc_pointer_available: bool
    memo_field_available: bool
    program_id_available: bool
    raw_instruction_ref_available: bool
    notes: str = ""


@dataclass(frozen=True)
class ValidationSummary:
    upstream_match_rate: float | None
    upstream_last_validated_at: str | None
    upstream_validation_status: str
    freshness_hours: float | None
    reconciliation_gate_passed: bool


def get_token_allowlist_status(run_query: QueryRunner, chain: str, token_symbol: str) -> bool:
    rows = run_query(TOKEN_ALLOWLIST_SQL, {"chain": chain, "token_symbol": token_symbol})
    return bool(rows)


def get_signal_availability(run_query: QueryRunner) -> SignalAvailability:
    rows = run_query(SIGNAL_AVAILABILITY_SQL, {})
    row = rows[0] if rows else {}
    return SignalAvailability(
        x402_signal_source_available=bool(row.get("x402_signal_source_available", False)),
        rpc_pointer_available=bool(row.get("rpc_pointer_available", False)),
        memo_field_available=bool(row.get("memo_field_available", False)),
        program_id_available=bool(row.get("program_id_available", False)),
        raw_instruction_ref_available=bool(row.get("raw_instruction_ref_available", False)),
        notes=str(row.get("notes") or ""),
    )


def get_freshness_rows(run_query: QueryRunner, chain: str, token_symbol: str) -> list[dict[str, Any]]:
    return run_query(FRESHNESS_SQL, {"chain": chain, "token_symbol": token_symbol})


def get_max_freshness_hours(run_query: QueryRunner, chain: str, token_symbol: str) -> float | None:
    rows = get_freshness_rows(run_query, chain, token_symbol)
    if not rows:
        return None
    values = [
        row.get("global_max_freshness_hours", row.get("freshness_hours"))
        for row in rows
        if row.get("global_max_freshness_hours", row.get("freshness_hours")) is not None
    ]
    return max(float(value) for value in values) if values else None


def get_latest_reconciliation_rows(
    run_query: QueryRunner, chain: str, token_symbol: str
) -> list[dict[str, Any]]:
    return run_query(RECONCILIATION_SQL, {"chain": chain, "token_symbol": token_symbol})


def get_upstream_validation_summary(
    run_query: QueryRunner,
    chain: str,
    token_symbol: str,
    freshness_threshold_hours: float = 8.0,
) -> ValidationSummary:
    max_freshness = get_max_freshness_hours(run_query, chain, token_symbol)
    reconciliation_rows = get_latest_reconciliation_rows(run_query, chain, token_symbol)
    reconciliation = reconciliation_rows[0] if reconciliation_rows else {}
    match_rate = reconciliation.get("match_rate")
    gate_passed = bool(reconciliation.get("gate_passed", False))
    last_validated_at = reconciliation.get("run_timestamp")

    if max_freshness is None or not reconciliation_rows:
        status = "unknown"
    elif max_freshness > freshness_threshold_hours:
        status = "stale"
    elif gate_passed and match_rate is not None and float(match_rate) >= 0.99:
        status = "validated"
    elif gate_passed:
        status = "partial"
    else:
        status = "partial"

    return ValidationSummary(
        upstream_match_rate=float(match_rate) if match_rate is not None else None,
        upstream_last_validated_at=str(last_validated_at) if last_validated_at is not None else None,
        upstream_validation_status=status,
        freshness_hours=max_freshness,
        reconciliation_gate_passed=gate_passed,
    )


def get_run_status_summary(health_payload: dict[str, Any]) -> dict[str, Any]:
    gates = health_payload.get("gates") if isinstance(health_payload, dict) else {}
    run_status = gates.get("run_status") if isinstance(gates, dict) else {}
    return run_status if isinstance(run_status, dict) else {"passed": False}
