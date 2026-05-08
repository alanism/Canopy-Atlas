"""Phase 11 monitoring, alert grouping, and outcome instrumentation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


ALERT_INVENTORY: dict[str, dict[str, str]] = {
    "correction_inbox_sla_breach": {
        "severity": "high",
        "root_cause": "label_operations",
        "description": "Route label correction inbox has unreviewed items past SLA.",
    },
    "missing_validation_gate_fields": {
        "severity": "critical",
        "root_cause": "validation_contract_drift",
        "description": "Validation payload is missing required gate fields.",
    },
    "stale_running_lock": {
        "severity": "critical",
        "root_cause": "pipeline_stale",
        "description": "A pipeline run stayed running beyond the overlap lock window.",
    },
    "upstream_health_non_ok": {
        "severity": "high",
        "root_cause": "upstream_stale",
        "description": "Upstream evidence health API returned degraded or unavailable status.",
    },
    "upstream_freshness_exceeded": {
        "severity": "high",
        "root_cause": "upstream_stale",
        "description": "Upstream evidence freshness exceeded the 8-hour threshold.",
    },
    "rpc_freshness_lag": {
        "severity": "high",
        "root_cause": "rpc_outage",
        "description": "RPC freshness lag is outside the acceptable range.",
    },
    "validation_failure": {
        "severity": "critical",
        "root_cause": "rpc_outage",
        "description": "Validation failed against expected reconciliation thresholds.",
    },
    "cache_stale": {
        "severity": "high",
        "root_cause": "rpc_outage",
        "description": "Cache payload is stale relative to expected metric cadence.",
    },
    "pipeline_stale": {
        "severity": "critical",
        "root_cause": "rpc_outage",
        "description": "Pipeline has not completed within expected cadence.",
    },
    "cache_unavailable": {
        "severity": "critical",
        "root_cause": "redis_outage",
        "description": "Cache backend is unavailable.",
    },
    "api_503": {
        "severity": "critical",
        "root_cause": "redis_outage",
        "description": "Public API returned cache-related 503 responses.",
    },
    "cache_promotion_failed": {
        "severity": "critical",
        "root_cause": "redis_outage",
        "description": "Validated payload could not be promoted to cache.",
    },
    "upstream_reconciliation_stale": {
        "severity": "high",
        "root_cause": "upstream_stale",
        "description": "Upstream evidence reconciliation evidence is stale.",
    },
    "no_new_validated_substrate": {
        "severity": "high",
        "root_cause": "upstream_stale",
        "description": "No new validated Upstream evidence substrate rows are available.",
    },
    "last_known_good_preserved": {
        "severity": "medium",
        "root_cause": "upstream_stale",
        "description": "System is serving last-known-good data while Upstream evidence is stale.",
    },
    "health_api_degraded": {
        "severity": "high",
        "root_cause": "upstream_stale",
        "description": "Upstream evidence health API is degraded.",
    },
}

ALERT_GROUPS: dict[str, tuple[str, ...]] = {
    "rpc_outage": ("rpc_freshness_lag", "validation_failure", "cache_stale", "pipeline_stale"),
    "redis_outage": ("cache_unavailable", "api_503", "cache_promotion_failed"),
    "upstream_stale": (
        "upstream_reconciliation_stale",
        "no_new_validated_substrate",
        "last_known_good_preserved",
        "health_api_degraded",
        "upstream_health_non_ok",
        "upstream_freshness_exceeded",
    ),
}

OUTCOME_METRICS = (
    "unique_v0_ips",
    "dashboard_summary_requests",
    "api_access_cta_clicks",
    "methodology_page_views",
    "correction_submissions",
    "serious_api_access_requests",
)


@dataclass(frozen=True)
class AlertEvent:
    alert_type: str
    severity: str
    root_cause: str
    message: str
    payload: dict[str, Any]
    emitted_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OutcomeInstrumentation:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.v0_ips: set[str] = set()

    def record_v0_request(self, *, path: str, ip_address: str | None) -> None:
        if ip_address:
            self.v0_ips.add(ip_address)
        if path.startswith("/v0/dashboard-summary"):
            self.counts["dashboard_summary_requests"] += 1
        if path.startswith("/v0/methodology"):
            self.counts["methodology_page_views"] += 1

    def record_event(self, event_name: str) -> None:
        if event_name not in OUTCOME_METRICS:
            raise ValueError(f"unsupported outcome metric: {event_name}")
        if event_name != "unique_v0_ips":
            self.counts[event_name] += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "unique_v0_ips": len(self.v0_ips),
            "dashboard_summary_requests": self.counts["dashboard_summary_requests"],
            "api_access_cta_clicks": self.counts["api_access_cta_clicks"],
            "methodology_page_views": self.counts["methodology_page_views"],
            "correction_submissions": self.counts["correction_submissions"],
            "serious_api_access_requests": self.counts["serious_api_access_requests"],
        }


def emit_alert(alert_type: str, *, message: str | None = None, payload: dict[str, Any] | None = None) -> AlertEvent:
    if alert_type not in ALERT_INVENTORY:
        raise ValueError(f"unsupported alert type: {alert_type}")
    definition = ALERT_INVENTORY[alert_type]
    return AlertEvent(
        alert_type=alert_type,
        severity=definition["severity"],
        root_cause=definition["root_cause"],
        message=message or definition["description"],
        payload=payload or {},
        emitted_at=datetime.now(timezone.utc).isoformat(),
    )


def group_alerts(alert_types: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for alert_type in alert_types:
        if alert_type not in ALERT_INVENTORY:
            raise ValueError(f"unsupported alert type: {alert_type}")
        root_cause = ALERT_INVENTORY[alert_type]["root_cause"]
        grouped.setdefault(root_cause, []).append(alert_type)
    return grouped


def evaluate_upstream_health_alerts(health: dict[str, Any]) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    status = health.get("status")
    if status and status != "ok":
        alerts.append(emit_alert("upstream_health_non_ok", payload={"status": status}))
    max_freshness = _max_freshness_hours(health)
    if max_freshness is not None and max_freshness > 8:
        alerts.append(emit_alert("upstream_freshness_exceeded", payload={"max_freshness_hours": max_freshness}))
    return alerts


def validate_required_gate_fields(payload: dict[str, Any]) -> list[AlertEvent]:
    required = ("freshness", "reconciliation", "run_status")
    gates = payload.get("gates") or {}
    missing = [field for field in required if field not in gates]
    if missing:
        return [emit_alert("missing_validation_gate_fields", payload={"missing": missing})]
    return []


def _max_freshness_hours(health: dict[str, Any]) -> float | None:
    gates = health.get("gates") or {}
    freshness = gates.get("freshness") or {}
    value = freshness.get("max_freshness_hours")
    if value is None:
        return None
    return float(value)
