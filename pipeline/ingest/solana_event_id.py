"""Deterministic raw event IDs for Solana/SVM transfer observations."""

from __future__ import annotations

import hashlib
from typing import Any


class EventIdError(ValueError):
    """Raised when an event cannot produce an unambiguous deterministic ID."""


def compute_solana_raw_event_id(event: dict[str, Any]) -> str:
    signature = event.get("signature")
    instruction_index = event.get("instruction_index")
    is_inner = event.get("is_inner")
    inner_instruction_index = event.get("inner_instruction_index")

    if not signature:
        raise EventIdError("Solana event requires signature")
    if instruction_index is None:
        raise EventIdError("Solana event requires instruction_index")
    if is_inner is None:
        raise EventIdError("Solana event requires is_inner")

    if is_inner is True:
        if inner_instruction_index is None:
            raise EventIdError("inner Solana event requires inner_instruction_index")
        if int(inner_instruction_index) < 0:
            raise EventIdError("inner_instruction_index must be non-negative")
        sentinel = int(inner_instruction_index)
    elif is_inner is False:
        if inner_instruction_index is not None:
            raise EventIdError("top-level Solana event must use inner_instruction_index=None")
        sentinel = -1
    else:
        raise EventIdError("is_inner must be a boolean")

    return f"solana_{signature}_{int(instruction_index)}_{sentinel}"


def compute_evm_raw_event_id(chain: str, event: dict[str, Any]) -> str:
    transaction_hash = event.get("transaction_hash")
    log_index = event.get("log_index")
    if not transaction_hash:
        raise EventIdError("EVM event requires transaction_hash")
    if log_index is None:
        raise EventIdError("EVM event requires log_index")
    key = f"{chain}:{transaction_hash}:{int(log_index)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def compute_raw_event_id(chain: str, event: dict[str, Any]) -> str:
    has_svm_keys = "signature" in event or "instruction_index" in event or "is_inner" in event
    has_evm_keys = "transaction_hash" in event or "log_index" in event

    if has_svm_keys and has_evm_keys:
        raise EventIdError("event has both SVM and EVM identity keys")
    if has_svm_keys:
        return compute_solana_raw_event_id(event)
    if has_evm_keys:
        return compute_evm_raw_event_id(chain, event)
    raise EventIdError("event missing chain-specific identity keys")
