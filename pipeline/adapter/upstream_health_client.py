"""Generic upstream health client boundary.

The public release uses this as an optional adapter contract for teams that
connect a warehouse, API, indexer, or oracle-like evidence source.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPECTED_CONTRACT_VERSION = "atlas-upstream-health-v1"
VALID_STATUSES = {"ok", "degraded", "unavailable"}


class UpstreamHealthError(RuntimeError):
    """Raised when the upstream health contract cannot be trusted."""


@dataclass(frozen=True)
class ServiceHealth:
    contract_version: str
    status: str
    suitable_for_runtime_routing: bool
    raw_response: dict[str, Any]
    http_status: int | None = None


HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()
    except URLError as exc:
        raise UpstreamHealthError(f"upstream health request failed: {exc}") from exc


def _require_gate(payload: dict[str, Any], gate_name: str) -> None:
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        raise UpstreamHealthError("upstream health payload missing gates object")
    gate = gates.get(gate_name)
    if not isinstance(gate, dict) or "passed" not in gate:
        raise UpstreamHealthError(f"upstream health payload missing {gate_name} gate")


def parse_service_health(payload: dict[str, Any], http_status: int | None = None) -> ServiceHealth:
    contract_version = payload.get("contract_version")
    if contract_version != EXPECTED_CONTRACT_VERSION:
        raise UpstreamHealthError("upstream health contract version mismatch")

    status = payload.get("status")
    if status not in VALID_STATUSES:
        raise UpstreamHealthError("upstream health payload has invalid status")

    if payload.get("suitable_for_runtime_routing") is not False:
        raise UpstreamHealthError("upstream health payload must be benchmark-only by default")

    _require_gate(payload, "freshness")
    _require_gate(payload, "reconciliation")
    _require_gate(payload, "run_status")

    return ServiceHealth(
        contract_version=contract_version,
        status=status,
        suitable_for_runtime_routing=False,
        raw_response=payload,
        http_status=http_status,
    )


def get_service_health(
    base_url: str | None = None,
    token: str | None = None,
    http_get: HttpGet = _default_http_get,
) -> ServiceHealth:
    base = (base_url or os.environ.get("ATLAS_UPSTREAM_API_BASE_URL") or "").rstrip("/")
    if not base:
        raise UpstreamHealthError("ATLAS_UPSTREAM_API_BASE_URL is required")

    bearer_token = token or os.environ.get("ATLAS_UPSTREAM_ID_TOKEN")
    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    http_status, body = http_get(f"{base}/health", headers)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpstreamHealthError("upstream health payload is not valid JSON") from exc

    health = parse_service_health(payload, http_status=http_status)
    if health.status == "unavailable" or http_status >= 500:
        raise UpstreamHealthError("upstream health is unavailable")
    return health
