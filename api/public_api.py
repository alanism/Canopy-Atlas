"""Framework-neutral public v0 API handlers."""

from __future__ import annotations

from typing import Any

from api.cache import CacheStore, SnapshotStore, cache_key, read_cache_first


ALLOWED_WINDOWS = {"15m", "1h", "24h", "7d"}
DEFAULT_DASHBOARD_TITLE = "Observed Stablecoin Route Benchmark"
METHODOLOGY_VERSION = "v0.1"


def unavailable_response() -> tuple[int, dict[str, str]]:
    return (
        503,
        {
            "error": "cache_temporarily_unavailable",
            "message": "Cache temporarily unavailable. Retry in 30 seconds.",
        },
    )


def bad_request(message: str) -> tuple[int, dict[str, str]]:
    return 400, {"error": "bad_request", "message": message}


def serve_cached_endpoint(
    *,
    endpoint: str,
    cache: CacheStore,
    snapshot_store: SnapshotStore | None = None,
    window: str | None = None,
    query_params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    params = query_params or {}
    if "refresh" in params:
        return bad_request("refresh is not available on public benchmark endpoints")
    if window is not None and window not in ALLOWED_WINDOWS:
        return bad_request("invalid window")

    result = read_cache_first(cache=cache, snapshot_store=snapshot_store, key=cache_key(endpoint, window))
    if result.payload is None:
        return unavailable_response()

    payload = ensure_public_envelope(result.payload)
    if result.warning:
        payload["meta"]["runtime_warning"] = result.warning
    return 200, payload


def dashboard_summary(
    *,
    cache: CacheStore,
    snapshot_store: SnapshotStore | None = None,
    window: str = "1h",
    query_params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(
        endpoint="dashboard-summary",
        cache=cache,
        snapshot_store=snapshot_store,
        window=window,
        query_params=query_params,
    )


def routes(cache: CacheStore, snapshot_store: SnapshotStore | None = None) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(endpoint="routes", cache=cache, snapshot_store=snapshot_store)


def fees(cache: CacheStore, snapshot_store: SnapshotStore | None = None) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(endpoint="fees", cache=cache, snapshot_store=snapshot_store)


def route_share(cache: CacheStore, snapshot_store: SnapshotStore | None = None) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(endpoint="route-share", cache=cache, snapshot_store=snapshot_store)


def reliability(cache: CacheStore, snapshot_store: SnapshotStore | None = None) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(endpoint="reliability", cache=cache, snapshot_store=snapshot_store)


def status(cache: CacheStore, snapshot_store: SnapshotStore | None = None) -> tuple[int, dict[str, Any]]:
    return serve_cached_endpoint(endpoint="status", cache=cache, snapshot_store=snapshot_store)


def methodology() -> tuple[int, dict[str, Any]]:
    return 200, {
        "meta": default_meta(),
        "data": {
            "methodology_version": METHODOLOGY_VERSION,
            "freshness_tier": "benchmark",
            "suitable_for_runtime_routing": False,
        },
    }


def ensure_public_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    meta = {**default_meta(), **payload.get("meta", {})}
    x402_signal_status = meta.get("x402_signal_status", "unavailable")
    meta["suitable_for_runtime_routing"] = False
    meta["freshness_tier"] = "benchmark"
    meta["x402_signal_detected"] = bool(meta.get("x402_signal_detected", False))
    if x402_signal_status != "detected":
        meta["dashboard_title"] = DEFAULT_DASHBOARD_TITLE
    return {**payload, "meta": meta}


def default_meta() -> dict[str, Any]:
    return {
        "cache_generation_timestamp": None,
        "metrics_timestamp": None,
        "data_window_start": None,
        "data_window_end": None,
        "last_validated_at": None,
        "data_quality_status": "unknown",
        "labeled_volume_pct": 0.0,
        "long_tail_volume_pct": 0.0,
        "methodology_version": METHODOLOGY_VERSION,
        "freshness_tier": "benchmark",
        "suitable_for_runtime_routing": False,
        "runtime_warning": None,
        "x402_signal_status": "unavailable",
        "x402_signal_detected": False,
        "dashboard_title": DEFAULT_DASHBOARD_TITLE,
    }
