"""Cache-first payload helpers for public API responses."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class CacheStore(Protocol):
    def get(self, key: str) -> str | None:
        ...

    def set(self, key: str, value: str) -> None:
        ...


class SnapshotStore(Protocol):
    def get_snapshot(self, key: str) -> dict[str, Any] | None:
        ...

    def set_snapshot(self, key: str, payload: dict[str, Any]) -> None:
        ...


@dataclass(frozen=True)
class CacheReadResult:
    status: str
    payload: dict[str, Any] | None
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemorySnapshotStore:
    def __init__(self) -> None:
        self.snapshots: dict[str, dict[str, Any]] = {}

    def get_snapshot(self, key: str) -> dict[str, Any] | None:
        return self.snapshots.get(key)

    def set_snapshot(self, key: str, payload: dict[str, Any]) -> None:
        self.snapshots[key] = payload


def cache_key(endpoint: str, window: str | None = None) -> str:
    suffix = f":{window}" if window else ""
    return f"v0:{endpoint}{suffix}"


def read_cache_first(
    *,
    cache: CacheStore,
    snapshot_store: SnapshotStore | None,
    key: str,
) -> CacheReadResult:
    try:
        cached = cache.get(key)
    except Exception:
        snapshot = snapshot_store.get_snapshot(key) if snapshot_store else None
        if snapshot is not None:
            return CacheReadResult(status="snapshot", payload=snapshot, warning="serving_last_known_good")
        return CacheReadResult(status="unavailable", payload=None, warning="cache_unavailable")

    if cached is None:
        return CacheReadResult(status="cold", payload=None, warning="cache_cold")

    payload = json.loads(cached)
    if snapshot_store is not None:
        snapshot_store.set_snapshot(key, payload)
    if payload.get("meta", {}).get("data_quality_status") == "stale":
        return CacheReadResult(status="stale", payload=payload, warning="cache_stale")
    return CacheReadResult(status="hit", payload=payload)


def promote_cache_payload(
    *,
    cache: CacheStore,
    snapshot_store: SnapshotStore | None,
    key: str,
    payload: dict[str, Any],
) -> None:
    encoded = json.dumps(payload, sort_keys=True)
    cache.set(key, encoded)
    if snapshot_store is not None:
        snapshot_store.set_snapshot(key, payload)
