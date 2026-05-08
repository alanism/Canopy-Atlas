"""Deterministic anti-gaming flag helpers."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AntiGamingFlag:
    flag_id: str
    route_id: str
    chain: str
    flag_type: str
    window_start: str
    window_end: str
    tx_count: int
    flag_status: str = "under_review"

    def merge_key(self) -> tuple[str, str, str, str]:
        return (self.route_id, self.chain, self.flag_type, self.window_start)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_flag_id(route_id: str, chain: str, flag_type: str, window_start: str) -> str:
    key = f"{route_id}|{chain}|{flag_type}|{window_start}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_self_transfer_flag(
    *,
    route_id: str,
    chain: str,
    window_start: str,
    window_end: str,
    tx_count: int,
) -> AntiGamingFlag:
    return AntiGamingFlag(
        flag_id=compute_flag_id(route_id, chain, "self_transfer", window_start),
        route_id=route_id,
        chain=chain,
        flag_type="self_transfer",
        window_start=window_start,
        window_end=window_end,
        tx_count=tx_count,
    )
