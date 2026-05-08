"""Private internal endpoint adapters."""

from __future__ import annotations

import os
from typing import Any

from api.auth import has_valid_bearer_token
from pipeline.orchestrator import AlertSink, PipelineRunStore, run_orchestrator


def internal_run(
    *,
    method: str,
    headers: dict[str, str],
    body: dict[str, Any],
    store: PipelineRunStore,
    alert_sink: AlertSink,
) -> tuple[int, dict[str, Any]]:
    if method.upper() != "POST":
        return 405, {"error": "method_not_allowed", "message": "POST required"}
    token = os.environ.get("ATLAS_ORCHESTRATOR_TOKEN", "").strip()
    if not token:
        return 503, {"error": "orchestrator_disabled", "message": "ATLAS_ORCHESTRATOR_TOKEN is not configured"}
    if not has_valid_bearer_token(headers, token):
        return 403, {"error": "forbidden", "message": "Valid orchestrator bearer token required"}
    try:
        result = run_orchestrator(payload=body, store=store, alert_sink=alert_sink)
    except ValueError as exc:
        return 400, {"error": "bad_request", "message": str(exc)}
    status_code = 200 if result.status in {"success", "skipped_overlap"} else 500
    return status_code, {"meta": {"private_endpoint": True}, "data": result.as_dict()}
