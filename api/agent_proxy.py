"""Paid AgentCash proxy for Canopy Atlas route policy access."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from api.auth import has_valid_bearer_token


API_VERSION = "0.1.0"
SUPPORTED_WINDOWS = {"15m", "1h", "24h", "7d"}
DEFAULT_WINDOW = "1h"
DEFAULT_LIMIT = 3
MAX_LIMIT = 10
DEFAULT_CHARGE_USDC = "0.05"
DEFAULT_PAYMENT_NETWORKS = ["base", "solana"]
PAYMENT_SIGNATURE_HEADERS = ("PAYMENT-SIGNATURE", "X-PAYMENT", "X-Payment")
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"
PAID_EVENT_TYPE = "canopy_paid_agent_event"
METRICS_WINDOWS = {"1h", "24h", "7d"}
DEFAULT_METRICS_WINDOW = "24h"


@dataclass(frozen=True)
class ProxyConfig:
    benchmark_api_base_url: str
    verifier_url: str
    verifier_token: str
    charge_usdc: str
    supported_payment_networks: list[str]
    wallet_rate_limit_per_min: int
    merchant_address_base: str | None = None
    merchant_address_solana: str | None = None
    admin_token: str = ""
    admin_dashboard_slug: str = "agentcash-ops"
    wallet_hash_salt: str = ""
    metrics_cache_dir: str = ""

    @classmethod
    def from_env(cls) -> "ProxyConfig":
        networks = [
            network.strip()
            for network in os.environ.get("SUPPORTED_PAYMENT_NETWORKS", ",".join(DEFAULT_PAYMENT_NETWORKS)).split(",")
            if network.strip()
        ]
        return cls(
            benchmark_api_base_url=os.environ.get("CANOPY_BENCHMARK_API_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
            verifier_url=os.environ.get("AGENTCASH_VERIFIER_URL", "").strip(),
            verifier_token=os.environ.get("AGENTCASH_VERIFIER_TOKEN", "").strip(),
            charge_usdc=os.environ.get("CHARGE_USDC", DEFAULT_CHARGE_USDC),
            supported_payment_networks=networks or DEFAULT_PAYMENT_NETWORKS,
            wallet_rate_limit_per_min=int(os.environ.get("WALLET_RATE_LIMIT_PER_MIN", "60")),
            merchant_address_base=os.environ.get("AGENTCASH_MERCHANT_ADDRESS_BASE") or None,
            merchant_address_solana=os.environ.get("AGENTCASH_MERCHANT_ADDRESS_SOLANA") or None,
            admin_token=os.environ.get("AGENTCASH_ADMIN_TOKEN", "").strip(),
            admin_dashboard_slug=os.environ.get("ADMIN_DASHBOARD_SLUG", "agentcash-ops").strip() or "agentcash-ops",
            wallet_hash_salt=os.environ.get("WALLET_HASH_SALT", "").strip(),
            metrics_cache_dir=os.environ.get("AGENTCASH_METRICS_CACHE_DIR", "").strip(),
        )


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    wallet: str | None = None
    payment_response: dict[str, Any] | None = None
    reason: str | None = None


class WalletRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = limit_per_minute
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, wallet: str, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        cutoff = current - 60
        with self._lock:
            recent = [timestamp for timestamp in self._requests.get(wallet, []) if timestamp >= cutoff]
            if len(recent) >= self.limit_per_minute:
                self._requests[wallet] = recent
                return False
            recent.append(current)
            self._requests[wallet] = recent
            return True


class PaidAgentEventRecorder:
    def emit(self, event: dict[str, Any]) -> None:
        print(json.dumps(event, sort_keys=True), file=sys.stdout, flush=True)


class FileMetricsCache:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def get_summary(self, window: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / metrics_cache_filename(window)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("meta", {}).get("window") != window:
            return None
        return payload


class HostedPaymentVerifier:
    def __init__(self, config: ProxyConfig) -> None:
        self.config = config

    def verify(self, *, headers: dict[str, str], request_body: dict[str, Any], path: str) -> VerificationResult:
        signature = first_header(headers, PAYMENT_SIGNATURE_HEADERS)
        if not signature:
            return VerificationResult(valid=False, reason="missing_payment_signature")
        if not self.config.verifier_url:
            return VerificationResult(valid=False, reason="verifier_not_configured")

        payload = {
            "protocol": "x402",
            "payment_signature": signature,
            "path": path,
            "method": "POST",
            "price": {"mode": "fixed", "currency": "USD", "amount": self.config.charge_usdc},
            "networks": self.config.supported_payment_networks,
            "request_body": request_body,
        }
        request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.verifier_token:
            request_headers["Authorization"] = f"Bearer {self.config.verifier_token}"

        request = Request(
            self.config.verifier_url,
            data=json.dumps(payload, sort_keys=True).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return VerificationResult(valid=False, reason=f"verifier_error:{exc.__class__.__name__}")

        valid = bool(response_payload.get("valid") or response_payload.get("success"))
        wallet = response_payload.get("wallet") or response_payload.get("address") or response_payload.get("payer")
        if not valid or not isinstance(wallet, str) or not wallet:
            return VerificationResult(valid=False, reason="verifier_rejected")
        return VerificationResult(valid=True, wallet=wallet, payment_response=response_payload)


class BenchmarkClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def dashboard_summary(self, window: str) -> tuple[int, dict[str, Any]]:
        query = urlencode({"window": window})
        request = Request(f"{self.base_url}/v0/dashboard-summary?{query}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except json.JSONDecodeError:
                payload = {"error": "upstream_error"}
            return exc.code, payload
        except (URLError, TimeoutError, json.JSONDecodeError):
            return 503, {"error": "upstream_unavailable"}


class AgentProxyHandler(BaseHTTPRequestHandler):
    config = ProxyConfig.from_env()
    verifier = HostedPaymentVerifier(config)
    benchmark_client = BenchmarkClient(config.benchmark_api_base_url)
    rate_limiter = WalletRateLimiter(config.wallet_rate_limit_per_min)
    event_recorder = PaidAgentEventRecorder()
    metrics_cache = FileMetricsCache(config.metrics_cache_dir)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._write_json(200, {"ok": True, "service": "canopy-agent-proxy"})
            return
        if parsed.path == "/openapi.json":
            self._write_json(200, paid_openapi_document(self.config))
            return
        if parsed.path == "/llms.txt":
            self._write_text(200, paid_agent_guidance(self.config), content_type="text/markdown; charset=utf-8")
            return
        if parsed.path == "/internal/agentcash-metrics":
            if not self._admin_authorized():
                self._write_json(403, {"error": "forbidden", "message": "Admin bearer token required."})
                return
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            window = query.get("window", DEFAULT_METRICS_WINDOW)
            if window not in METRICS_WINDOWS:
                self._write_json(400, {"error": "bad_request", "message": "window must be one of 1h, 24h, 7d."})
                return
            payload = self.metrics_cache.get_summary(window) or empty_agentcash_metrics_summary(window)
            self._write_json(200, payload)
            return
        if parsed.path == f"/ops/{self.config.admin_dashboard_slug}":
            if not self._admin_authorized():
                self._write_text(403, "Forbidden", content_type="text/plain; charset=utf-8")
                return
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            window = query.get("window", DEFAULT_METRICS_WINDOW)
            if window not in METRICS_WINDOWS:
                window = DEFAULT_METRICS_WINDOW
            payload = self.metrics_cache.get_summary(window) or empty_agentcash_metrics_summary(window)
            self._write_text(200, render_agentcash_dashboard(payload), content_type="text/html; charset=utf-8")
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/v1/route-policy":
            self._write_json(404, {"error": "not_found"})
            return

        started_at = time.time()
        status_code, parsed_body = parse_route_policy_body(self._read_json_body())
        if status_code != 200:
            self._emit_paid_event(
                outcome="bad_request",
                path=parsed.path,
                status_code=status_code,
                started_at=started_at,
                request_body={},
                reason=parsed_body.get("message"),
            )
            self._write_json(status_code, parsed_body)
            return

        headers = {key: value for key, value in self.headers.items()}
        verification = self.verifier.verify(headers=headers, request_body=parsed_body, path=parsed.path)
        if not verification.valid:
            payment_body, payment_headers = payment_required_response(self.config, parsed.path, verification.reason)
            self._emit_paid_event(
                outcome=payment_failure_outcome(verification.reason),
                path=parsed.path,
                status_code=402,
                started_at=started_at,
                request_body=parsed_body,
                verification=verification,
                reason=verification.reason,
            )
            self._write_json(402, payment_body, extra_headers=payment_headers)
            return

        assert verification.wallet is not None
        if not self.rate_limiter.allow(verification.wallet):
            self._emit_paid_event(
                outcome="rate_limited",
                path=parsed.path,
                status_code=429,
                started_at=started_at,
                request_body=parsed_body,
                verification=verification,
                wallet=verification.wallet,
            )
            self._write_json(
                429,
                {
                    "error": "rate_limited",
                    "message": "Wallet rate limit exceeded.",
                    "limit_per_minute": self.config.wallet_rate_limit_per_min,
                },
            )
            return

        upstream_status, upstream_payload = self.benchmark_client.dashboard_summary(parsed_body["window"])
        if upstream_status != 200:
            self._emit_paid_event(
                outcome="benchmark_unavailable",
                path=parsed.path,
                status_code=503,
                started_at=started_at,
                request_body=parsed_body,
                verification=verification,
                wallet=verification.wallet,
                upstream_status=upstream_status,
            )
            self._write_json(
                503,
                {
                    "error": "benchmark_unavailable",
                    "message": "Benchmark source is unavailable; no paid route policy result was returned.",
                    "upstream_status": upstream_status,
                },
            )
            return

        response = route_policy_response(
            benchmark_payload=upstream_payload,
            request_body=parsed_body,
            wallet=verification.wallet,
            charge_usdc=self.config.charge_usdc,
        )
        extra_headers = {}
        if verification.payment_response:
            extra_headers[PAYMENT_RESPONSE_HEADER] = base64_json(verification.payment_response)
        self._emit_paid_event(
            outcome="paid_success",
            path=parsed.path,
            status_code=200,
            started_at=started_at,
            request_body=parsed_body,
            verification=verification,
            wallet=verification.wallet,
            upstream_status=upstream_status,
        )
        self._write_json(200, response, extra_headers=extra_headers)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> Any:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            return {"__invalid_json__": True}

    def _write_json(self, status_code: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _write_text(self, status_code: int, body: str, *, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _admin_authorized(self) -> bool:
        return has_valid_bearer_token(dict(self.headers.items()), self.config.admin_token)

    def _emit_paid_event(
        self,
        *,
        outcome: str,
        path: str,
        status_code: int,
        started_at: float,
        request_body: dict[str, Any],
        verification: VerificationResult | None = None,
        wallet: str | None = None,
        upstream_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        event = build_paid_agent_event(
            config=self.config,
            outcome=outcome,
            path=path,
            status_code=status_code,
            started_at=started_at,
            request_body=request_body,
            verification=verification,
            wallet=wallet,
            upstream_status=upstream_status,
            reason=reason,
        )
        self.event_recorder.emit(event)


def parse_route_policy_body(value: Any) -> tuple[int, dict[str, Any]]:
    if isinstance(value, dict) and value.get("__invalid_json__"):
        return 400, {"error": "bad_request", "message": "Invalid JSON body."}
    if value is None:
        value = {}
    if not isinstance(value, dict):
        return 400, {"error": "bad_request", "message": "Request body must be a JSON object."}

    window = value.get("window", DEFAULT_WINDOW)
    if window not in SUPPORTED_WINDOWS:
        return 400, {"error": "bad_request", "message": "window must be one of 15m, 1h, 24h, 7d."}

    limit = value.get("limit", DEFAULT_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int):
        return 400, {"error": "bad_request", "message": "limit must be an integer."}
    if limit < 1 or limit > MAX_LIMIT:
        return 400, {"error": "bad_request", "message": "limit must be between 1 and 10."}

    return 200, {"window": window, "limit": limit}


def build_paid_agent_event(
    *,
    config: ProxyConfig,
    outcome: str,
    path: str,
    status_code: int,
    started_at: float,
    request_body: dict[str, Any],
    verification: VerificationResult | None = None,
    wallet: str | None = None,
    upstream_status: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    emitted_at = datetime.now(timezone.utc).isoformat()
    latency_ms = round((time.time() - started_at) * 1000, 3)
    wallet_id = anonymized_wallet_id(wallet, config.wallet_hash_salt)
    network = payment_network(verification.payment_response if verification else None)
    event_id = stable_event_id(
        emitted_at=emitted_at,
        outcome=outcome,
        path=path,
        status_code=status_code,
        wallet_id=wallet_id,
        request_body=request_body,
        upstream_status=upstream_status,
    )
    return {
        "event_type": PAID_EVENT_TYPE,
        "event_id": event_id,
        "emitted_at": emitted_at,
        "service": "canopy-agent-proxy",
        "path": path,
        "outcome": outcome,
        "status_code": status_code,
        "window": request_body.get("window"),
        "limit": request_body.get("limit"),
        "charge_usdc": config.charge_usdc,
        "payment_network": network,
        "verifier_reason": reason,
        "upstream_status": upstream_status,
        "latency_ms": latency_ms,
        "wallet_id": wallet_id,
        "wallet_hash_salt_configured": bool(config.wallet_hash_salt),
    }


def stable_event_id(
    *,
    emitted_at: str,
    outcome: str,
    path: str,
    status_code: int,
    wallet_id: str | None,
    request_body: dict[str, Any],
    upstream_status: int | None,
) -> str:
    payload = json.dumps(
        {
            "emitted_at": emitted_at,
            "outcome": outcome,
            "path": path,
            "status_code": status_code,
            "wallet_id": wallet_id,
            "window": request_body.get("window"),
            "limit": request_body.get("limit"),
            "upstream_status": upstream_status,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def anonymized_wallet_id(wallet: str | None, salt: str) -> str | None:
    if not wallet or not salt:
        return None
    digest = hmac.new(salt.encode("utf-8"), wallet.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"wallet_{digest[:16]}"


def payment_network(payment_response: dict[str, Any] | None) -> str | None:
    if not payment_response:
        return None
    for key in ("network", "payment_network", "chain"):
        value = payment_response.get(key)
        if isinstance(value, str) and value:
            return value
    payment = payment_response.get("payment")
    if isinstance(payment, dict):
        value = payment.get("network") or payment.get("chain")
        if isinstance(value, str) and value:
            return value
    return None


def payment_failure_outcome(reason: str | None) -> str:
    if reason == "missing_payment_signature":
        return "payment_required"
    return "payment_rejected"


def route_policy_response(
    *,
    benchmark_payload: dict[str, Any],
    request_body: dict[str, Any],
    wallet: str,
    charge_usdc: str,
) -> dict[str, Any]:
    rows = (
        benchmark_payload.get("data", {})
        .get("panels", {})
        .get("observed_effective_cost_leaderboard", [])
    )
    candidates = [route_policy_candidate(row, rank) for rank, row in enumerate(rows[: request_body["limit"]], start=1)]
    benchmark_meta = benchmark_payload.get("meta", {})
    return {
        "meta": {
            "service": "canopy-agent-proxy",
            "api_version": API_VERSION,
            "payment_status": "paid",
            "charged_usdc": charge_usdc,
            "wallet": wallet,
            "freshness_tier": "benchmark",
            "suitable_for_runtime_routing": False,
            "benchmark_window": request_body["window"],
            "benchmark_metadata": {
                "metrics_timestamp": benchmark_meta.get("metrics_timestamp"),
                "last_validated_at": benchmark_meta.get("last_validated_at"),
                "data_quality_status": benchmark_meta.get("data_quality_status"),
                "x402_signal_status": benchmark_meta.get("x402_signal_status"),
            },
            "warning": "Benchmark evidence only. Do not use this response as live autonomous route execution.",
        },
        "data": {
            "policy_type": "minimal_benchmark_route_policy",
            "candidates": candidates,
        },
    }


def route_policy_candidate(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "route_id": row.get("route_id"),
        "observed_cost_pct": row.get("observed_cost_pct"),
        "route_share_pct": row.get("route_share_pct"),
        "observed_settlement_rate": row.get("observed_settlement_rate"),
        "data_quality_status": row.get("data_quality_status"),
        "suitable_for_runtime_routing": False,
    }


def payment_required_response(
    config: ProxyConfig,
    path: str,
    reason: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    requirement = payment_requirement(config, path)
    body = {
        "error": "payment_required",
        "message": "Payment is required to call POST /v1/route-policy.",
        "reason": reason,
        "payment": requirement,
    }
    return body, {PAYMENT_REQUIRED_HEADER: base64_json(requirement)}


def payment_requirement(config: ProxyConfig, path: str) -> dict[str, Any]:
    return {
        "version": "2",
        "service": "canopy-agent-proxy",
        "resource": path,
        "method": "POST",
        "description": "Canopy Atlas paid benchmark route-policy interaction.",
        "price": {"mode": "fixed", "currency": "USD", "amount": config.charge_usdc},
        "accepts": [
            {
                "protocol": "x402",
                "scheme": "exact",
                "network": network,
                "currency": "USDC",
                "amount_usd": config.charge_usdc,
                "pay_to": merchant_address_for_network(config, network),
            }
            for network in config.supported_payment_networks
        ],
    }


def merchant_address_for_network(config: ProxyConfig, network: str) -> str | None:
    if network == "base":
        return config.merchant_address_base
    if network == "solana":
        return config.merchant_address_solana
    return None


def paid_openapi_document(config: ProxyConfig) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Canopy Atlas Agent Proxy",
            "version": API_VERSION,
            "description": "Paid AgentCash-compatible route policy proxy for benchmark-grade Canopy Atlas evidence.",
            "x-guidance": (
                "Use POST /v1/route-policy for the paid $0.05 route-policy interaction. "
                "The response is benchmark evidence only and is not suitable for live autonomous route execution."
            ),
        },
        "servers": [{"url": "/", "description": "Current paid proxy origin"}],
        "paths": {
            "/healthz": {
                "get": {
                    "operationId": "getProxyHealth",
                    "summary": "Get paid proxy health",
                    "responses": {"200": _json_response("Health response", "Health")},
                }
            },
            "/v1/route-policy": {
                "post": {
                    "operationId": "createRoutePolicy",
                    "summary": "Create a paid benchmark route policy",
                    "tags": ["Paid Route Policy"],
                    "x-payment-info": {
                        "price": {"mode": "fixed", "currency": "USD", "amount": config.charge_usdc},
                        "protocols": [{"x402": {"networks": config.supported_payment_networks}}],
                    },
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoutePolicyRequest"}}},
                    },
                    "responses": {
                        "200": _json_response("Paid benchmark route policy", "RoutePolicyResponse"),
                        "400": _json_response("Bad request", "Error"),
                        "402": {"description": "Payment Required"},
                        "429": _json_response("Rate limited", "Error"),
                        "503": _json_response("Benchmark unavailable", "Error"),
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Health": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}, "service": {"type": "string"}},
                    "required": ["ok", "service"],
                },
                "RoutePolicyRequest": {
                    "type": "object",
                    "properties": {
                        "window": {"type": "string", "enum": sorted(SUPPORTED_WINDOWS), "default": DEFAULT_WINDOW},
                        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT},
                    },
                    "additionalProperties": False,
                },
                "RoutePolicyResponse": {
                    "type": "object",
                    "properties": {
                        "meta": {"type": "object", "additionalProperties": True},
                        "data": {
                            "type": "object",
                            "properties": {
                                "policy_type": {"type": "string"},
                                "candidates": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                            },
                            "required": ["policy_type", "candidates"],
                        },
                    },
                    "required": ["meta", "data"],
                },
                "Error": {
                    "type": "object",
                    "properties": {"error": {"type": "string"}, "message": {"type": "string"}},
                    "required": ["error"],
                },
            }
        },
    }


def paid_agent_guidance(config: ProxyConfig) -> str:
    networks = ", ".join(config.supported_payment_networks)
    return f"""# Canopy Atlas Paid Agent Proxy

Start with `GET /openapi.json`, then call `POST /v1/route-policy`.

`POST /v1/route-policy` costs ${config.charge_usdc} and supports AgentCash/x402 payment on: {networks}.

Request body:

```json
{{"window":"1h","limit":3}}
```

The result is benchmark evidence only. It is not a wallet, payment processor, live routing oracle, or autonomous route executor.
"""


def first_header(headers: dict[str, str], names: tuple[str, ...]) -> str | None:
    lower = {key.lower(): value for key, value in headers.items()}
    for name in names:
        value = lower.get(name.lower())
        if value:
            return value
    return None


def base64_json(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")


def metrics_cache_filename(window: str) -> str:
    if window not in METRICS_WINDOWS:
        raise ValueError("unsupported metrics window")
    return f"agentcash_metrics_summary_{window}.json"


def empty_agentcash_metrics_summary(window: str) -> dict[str, Any]:
    return {
        "meta": {
            "service": "canopy-agent-proxy",
            "window": window,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "append_only_paid_agent_events",
            "wallet_privacy": "hmac_anonymized",
            "data_quality_status": "empty",
            "settlement_note": "No cached AgentCash metrics aggregate is available yet.",
        },
        "data": {
            "totals": {
                "paid_success_count": 0,
                "gross_usdc": "0.00",
                "payment_required_count": 0,
                "payment_rejected_count": 0,
                "rate_limited_count": 0,
                "benchmark_unavailable_count": 0,
                "unique_payer_wallets": 0,
                "p95_latency_ms": None,
            },
            "breakdowns": {"by_network": [], "by_window_requested": [], "top_wallets": []},
            "latest_events": [],
        },
    }


def render_agentcash_dashboard(payload: dict[str, Any]) -> str:
    meta = payload.get("meta", {})
    data = payload.get("data", {})
    totals = data.get("totals", {})
    breakdowns = data.get("breakdowns", {})
    latest_events = data.get("latest_events", [])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Canopy AgentCash Ops</title>
  <style>
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f5f2; color: #1d2622; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 22px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; letter-spacing: 0; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; letter-spacing: 0; }}
    p {{ margin: 0; color: #59645f; }}
    .status {{ text-align: right; font-size: 13px; color: #59645f; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .panel {{ background: #fff; border: 1px solid #d8ddd6; border-radius: 8px; padding: 16px; }}
    .metric span {{ display: block; color: #66716c; font-size: 12px; margin-bottom: 6px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e3e6e1; padding: 10px 8px; text-align: left; }}
    th {{ color: #66716c; font-weight: 600; }}
    .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }}
    @media (max-width: 900px) {{ .grid, .two {{ grid-template-columns: 1fr; }} header {{ display: block; }} .status {{ text-align: left; margin-top: 12px; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Canopy AgentCash Ops</h1>
      <p>Private paid-agent metrics from append-only proxy events.</p>
    </div>
    <div class="status">Window: {esc(meta.get("window"))}<br />Generated: {esc(meta.get("generated_at"))}<br />Quality: {esc(meta.get("data_quality_status"))}</div>
  </header>
  <section class="grid">
    {metric_card("Paid Calls", totals.get("paid_success_count"))}
    {metric_card("Gross USDC", totals.get("gross_usdc"))}
    {metric_card("Unique Payers", totals.get("unique_payer_wallets"))}
    {metric_card("p95 Latency", format_ms(totals.get("p95_latency_ms")))}
    {metric_card("Payment Required", totals.get("payment_required_count"))}
    {metric_card("Verifier Rejects", totals.get("payment_rejected_count"))}
    {metric_card("Rate Limited", totals.get("rate_limited_count"))}
    {metric_card("Benchmark 503", totals.get("benchmark_unavailable_count"))}
  </section>
  <section class="panel" style="margin-bottom:18px;"><h2>Settlement / Wallet Note</h2><p>{esc(meta.get("settlement_note") or "Run npx agentcash@latest balance from an operator shell for current merchant wallet balance.")}</p></section>
  <section class="two">
    {table_panel("Payment Networks", breakdowns.get("by_network", []), ("network", "count", "gross_usdc"))}
    {table_panel("Requested Windows", breakdowns.get("by_window_requested", []), ("window", "count", "gross_usdc"))}
  </section>
  <section class="two">
    {table_panel("Top Wallets", breakdowns.get("top_wallets", []), ("wallet_id", "paid_success_count", "gross_usdc"))}
    {table_panel("Latest Events", latest_events, ("emitted_at", "outcome", "wallet_id"))}
  </section>
</main>
</body>
</html>"""


def metric_card(label: str, value: Any) -> str:
    return f'<div class="panel metric"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'


def table_panel(title: str, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    header = "".join(f"<th>{esc(column)}</th>" for column in columns)
    if rows:
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(row.get(column))}</td>" for column in columns) + "</tr>"
            for row in rows[:10]
        )
    else:
        body = f'<tr><td colspan="{len(columns)}">No rows.</td></tr>'
    return f'<section class="panel"><h2>{esc(title)}</h2><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></section>'


def format_ms(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f} ms"
    except (TypeError, ValueError):
        return "-"


def esc(value: Any) -> str:
    if value is None:
        return "-"
    return html.escape(str(value), quote=True)


def _json_response(description: str, schema_name: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AgentProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
