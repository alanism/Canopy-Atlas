"""Minimal Cloud Run HTTP server for Canopy Atlas public/private endpoints."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api.auth import has_valid_bearer_token
from api.cache import cache_key, promote_cache_payload
from api.discovery import agent_guidance_text, endpoint_index, openapi_document
from api.payloads import build_dashboard_summary_payload, build_investor_preview_dashboard_payload
from api.public_api import (
    dashboard_summary,
    fees,
    methodology,
    reliability,
    route_share,
    routes,
    status,
)
from pipeline.monitoring import OutcomeInstrumentation


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


CACHE = MemoryCache()
OUTCOMES = OutcomeInstrumentation()


def bootstrap_cache() -> None:
    if os.environ.get("CANOPY_BOOTSTRAP_EMPTY_CACHE") != "1":
        return
    if os.environ.get("CANOPY_BOOTSTRAP_PREVIEW_ROWS", "1") == "1":
        payload = build_investor_preview_dashboard_payload()
    else:
        payload = build_dashboard_summary_payload(
            meta={
                "cache_generation_timestamp": None,
                "metrics_timestamp": None,
                "last_validated_at": None,
                "data_quality_status": "unknown",
                "labeled_volume_pct": 0.0,
                "long_tail_volume_pct": 0.0,
                "x402_signal_status": "unavailable",
                "x402_signal_detected": False,
                "runtime_warning": "Public sample bootstrap cache. Scheduled cache refresh not observed yet.",
            },
            leaderboard=[],
            route_share=[],
            settlement_health=[],
        )
    for key in (
        cache_key("dashboard-summary", "1h"),
        cache_key("dashboard-summary", "15m"),
        cache_key("dashboard-summary", "24h"),
        cache_key("dashboard-summary", "7d"),
    ):
        promote_cache_payload(cache=CACHE, snapshot_store=None, key=key, payload=payload)
    promote_cache_payload(
        cache=CACHE,
        snapshot_store=None,
        key=cache_key("status"),
        payload={"meta": payload["meta"], "data": {"status": "sample_bootstrap"}},
    )


class CanopyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        if parsed.path == "/v0" or parsed.path.startswith("/v0/"):
            OUTCOMES.record_v0_request(path=parsed.path, ip_address=self.client_address[0])

        if parsed.path == "/healthz":
            self._write_json(200, {"ok": True})
            return
        if parsed.path == "/internal/outcome-metrics":
            self._write_json(200, {"data": OUTCOMES.snapshot()})
            return
        if parsed.path == "/openapi.json":
            self._write_json(200, openapi_document())
            return
        if parsed.path in {"/llms.txt", "/agents.txt"}:
            self._write_text(200, agent_guidance_text(), content_type="text/markdown; charset=utf-8")
            return
        if parsed.path == "/v0":
            self._write_json(200, endpoint_index())
            return
        if parsed.path == "/v0/methodology":
            self._write_json(*methodology())
            return
        if parsed.path == "/docs/integration-guide":
            self._write_text(200, _integration_guide(), content_type="text/markdown; charset=utf-8")
            return
        if parsed.path == "/v0/dashboard-summary":
            self._write_json(*dashboard_summary(cache=CACHE, window=query.get("window", "1h"), query_params=query))
            return
        if parsed.path == "/v0/routes":
            self._write_json(*routes(CACHE))
            return
        if parsed.path == "/v0/fees":
            self._write_json(*fees(CACHE))
            return
        if parsed.path == "/v0/route-share":
            self._write_json(*route_share(CACHE))
            return
        if parsed.path == "/v0/reliability":
            self._write_json(*reliability(CACHE))
            return
        if parsed.path == "/v0/status":
            self._write_json(*status(CACHE))
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/internal/run":
            token = os.environ.get("ATLAS_ORCHESTRATOR_TOKEN", "").strip()
            if not token:
                self._write_json(503, {"error": "orchestrator_disabled", "message": "ATLAS_ORCHESTRATOR_TOKEN is not configured."})
                return
            if not has_valid_bearer_token(dict(self.headers.items()), token):
                self._write_json(403, {"error": "forbidden", "message": "Valid orchestrator bearer token required"})
                return
            self._write_json(501, {"error": "not_implemented", "message": "Pipeline store binding is not configured."})
            return
        self._write_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write_json(self, status_code: int, payload: dict) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_text(self, status_code: int, body: str, *, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _integration_guide() -> str:
    return (Path(__file__).resolve().parents[1] / "docs" / "integration-guide.md").read_text(encoding="utf-8")


def main() -> None:
    bootstrap_cache()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CanopyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
