"""Schema checks for a generic upstream x402 evidence contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline.adapter.upstream_gates import QueryRunner, TOKEN_ALLOWLIST_SQL


TRANSFER_CONTRACT_COLUMNS_SQL = """
SELECT column_name
FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'upstream_evidence_contract_v1'
"""

TRANSFER_SAMPLE_SQL = """
SELECT
  chain,
  token_symbol,
  signature,
  instruction_index,
  is_inner,
  inner_instruction_index
FROM `{project}.{dataset}.upstream_evidence_contract_v1`
WHERE token_symbol = @token_symbol
  AND chain = @chain
LIMIT @limit
"""

REQUIRED_TRANSFER_FIELDS = {
    "chain",
    "block_timestamp",
    "transaction_hash",
    "log_index",
    "signature",
    "instruction_index",
    "is_inner",
    "inner_instruction_index",
    "from_address",
    "to_address",
    "token_address",
    "token_symbol",
    "amount_raw",
    "decimals",
    "amount_tokens",
    "block_date",
}

SOLANA_IDENTITY_FIELDS = {
    "signature",
    "instruction_index",
    "is_inner",
    "inner_instruction_index",
}


@dataclass(frozen=True)
class SchemaCheckResult:
    passed: bool
    missing_fields: list[str]
    token_symbol_check_passed: bool
    notes: str
    target_tables: list[str]


def validate_schema_and_identity(
    run_query: QueryRunner,
    chain: str,
    token_symbol: str,
) -> SchemaCheckResult:
    column_rows = run_query(TRANSFER_CONTRACT_COLUMNS_SQL, {})
    available_fields = {str(row.get("column_name")) for row in column_rows if row.get("column_name")}
    missing_fields = sorted(REQUIRED_TRANSFER_FIELDS - available_fields)

    token_rows = run_query(TOKEN_ALLOWLIST_SQL, {"chain": chain, "token_symbol": token_symbol})
    token_symbol_check_passed = bool(token_rows)

    sample_rows = run_query(TRANSFER_SAMPLE_SQL, {"chain": chain, "token_symbol": token_symbol, "limit": 10})
    notes = "Upstream evidence contract exposes top-level Solana identity; inner rows require explicit source support."
    if chain == "solana":
        invalid_identity_rows = [
            row
            for row in sample_rows
            if row.get("signature") is None or row.get("instruction_index") is None or row.get("is_inner") is None
        ]
        if invalid_identity_rows:
            missing_fields.extend(sorted(SOLANA_IDENTITY_FIELDS & available_fields))
            notes = "One or more Solana sample rows are missing required identity values."

    return SchemaCheckResult(
        passed=not missing_fields and token_symbol_check_passed,
        missing_fields=sorted(set(missing_fields)),
        token_symbol_check_passed=token_symbol_check_passed,
        notes=notes,
        target_tables=["upstream_evidence_contract_v1"],
    )
