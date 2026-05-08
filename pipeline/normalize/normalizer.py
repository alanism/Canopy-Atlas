"""Normalize raw upstream evidence events into x402 payment staging rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pipeline.adapter.generic_adapter import RawEvidenceEventStage
from pipeline.ingest.solana_event_id import compute_raw_event_id


FEE_STATUSES = {
    "direct_observed",
    "inferred_from_schedule",
    "estimated",
    "unavailable",
    "not_observed",
}


class NormalizationError(ValueError):
    """Raised when a staged event cannot be normalized deterministically."""


@dataclass(frozen=True)
class NormalizedPaymentStage:
    chain: str
    transaction_hash: str | None
    signature: str | None
    log_index: int | None
    instruction_index: int | None
    is_inner: bool
    inner_instruction_index: int | None
    block_timestamp: str
    block_date: str
    block_number: int
    from_address: str
    to_address: str
    amount_tokens: float | None
    amount_usd: float | None
    token_symbol: str
    route_id: str
    protocol_type: str
    payment_scheme: str
    payment_structure: str
    settlement_node_id: str
    settlement_node_name: str
    settlement_node_type: str
    payment_role: str
    label_confidence: str
    network_fee_usd: float
    priority_fee_usd: float | None
    facilitator_fee_usd: float | None
    network_fee_observation_status: str
    priority_fee_observation_status: str
    facilitator_fee_observation_status: str
    total_observed_fee_usd: float
    fee_source: str
    fee_model: str
    observed_onchain_settled: bool
    settlement_latency_ms: int | None
    self_transfer_flag: bool
    normalized_payment_id: str
    source_path: str
    decode_version: str
    run_id: str
    validation_status: str
    last_validated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_raw_event(
    raw_event: RawEvidenceEventStage,
    *,
    last_validated_at: str,
) -> NormalizedPaymentStage:
    payload = raw_event.raw_payload
    chain = str(payload["chain"])
    token_symbol = str(payload["token_symbol"])
    settlement_node_id = str(payload.get("settlement_node_id") or "unknown_long_tail")
    route_id = f"{chain}_{token_symbol}_{settlement_node_id}"

    x402_signal_detected = bool(raw_event.x402_signal_detected or payload.get("x402_signal_detected", False))
    protocol_type = "x402_facilitator" if x402_signal_detected else "unknown"

    amount_tokens = _optional_float(payload.get("amount_tokens", payload.get("amount_token")))
    amount_usd = _optional_float(payload.get("amount_usd_proxy"))
    network_fee_usd = _optional_float(payload.get("fee_usd_proxy")) or 0.0
    priority_fee_usd = _optional_float(payload.get("priority_fee_usd"))
    facilitator_fee_usd = _optional_float(payload.get("facilitator_fee_usd"))
    total_observed_fee_usd = network_fee_usd + (priority_fee_usd or 0.0) + (facilitator_fee_usd or 0.0)

    normalized_payment_id = compute_raw_event_id(chain, _identity_payload(chain, payload))
    if normalized_payment_id != raw_event.raw_event_id:
        raise NormalizationError("raw_event_id mismatch during normalization")

    return NormalizedPaymentStage(
        chain=chain,
        transaction_hash=payload.get("transaction_hash"),
        signature=payload.get("signature"),
        log_index=_optional_int(payload.get("log_index")),
        instruction_index=_optional_int(payload.get("instruction_index")),
        is_inner=bool(payload.get("is_inner", False)),
        inner_instruction_index=_optional_int(payload.get("inner_instruction_index")),
        block_timestamp=str(payload["block_timestamp"]),
        block_date=str(payload["block_date"]),
        block_number=int(payload["block_number"]),
        from_address=str(payload["from_address"]),
        to_address=str(payload["to_address"]),
        amount_tokens=amount_tokens,
        amount_usd=amount_usd,
        token_symbol=token_symbol,
        route_id=route_id,
        protocol_type=protocol_type,
        payment_scheme=str(payload.get("payment_scheme") or "unknown"),
        payment_structure=str(payload.get("payment_structure") or "unknown"),
        settlement_node_id=settlement_node_id,
        settlement_node_name=str(payload.get("settlement_node_name") or "Unknown / Decentralized Long Tail"),
        settlement_node_type=str(payload.get("settlement_node_type") or "unknown"),
        payment_role=str(payload.get("payment_role") or "unknown"),
        label_confidence=str(payload.get("label_confidence") or "unknown"),
        network_fee_usd=network_fee_usd,
        priority_fee_usd=priority_fee_usd,
        facilitator_fee_usd=facilitator_fee_usd,
        network_fee_observation_status=_status_or_default(payload.get("network_fee_observation_status"), "direct_observed"),
        priority_fee_observation_status=_status_or_default(payload.get("priority_fee_observation_status"), "not_observed"),
        facilitator_fee_observation_status=_status_or_default(
            payload.get("facilitator_fee_observation_status"), "unavailable"
        ),
        total_observed_fee_usd=total_observed_fee_usd,
        fee_source=str(payload.get("fee_source") or "bq_derived"),
        fee_model=str(payload.get("fee_model") or "unknown"),
        observed_onchain_settled=True,
        settlement_latency_ms=_optional_int(payload.get("settlement_latency_ms")),
        self_transfer_flag=str(payload["from_address"]) == str(payload["to_address"]),
        normalized_payment_id=normalized_payment_id,
        source_path=raw_event.source_path,
        decode_version=raw_event.decode_version,
        run_id=raw_event.run_id,
        validation_status=str(payload.get("validation_status") or "stale"),
        last_validated_at=last_validated_at,
    )


def solana_merge_key(row: NormalizedPaymentStage) -> tuple[str, str | None, int | None, bool, int]:
    if row.chain != "solana":
        raise NormalizationError("solana_merge_key requires chain=solana")
    return (
        row.chain,
        row.signature,
        row.instruction_index,
        row.is_inner,
        row.inner_instruction_index if row.inner_instruction_index is not None else -1,
    )


def _identity_payload(chain: str, payload: dict[str, Any]) -> dict[str, Any]:
    if chain == "solana":
        return {
            "signature": payload.get("signature"),
            "instruction_index": payload.get("instruction_index"),
            "is_inner": payload.get("is_inner"),
            "inner_instruction_index": payload.get("inner_instruction_index"),
        }
    return {
        "transaction_hash": payload.get("transaction_hash"),
        "log_index": payload.get("log_index"),
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _status_or_default(value: Any, default: str) -> str:
    status = str(value) if value is not None else default
    if status not in FEE_STATUSES:
        raise NormalizationError(f"invalid fee observation status: {status}")
    return status
