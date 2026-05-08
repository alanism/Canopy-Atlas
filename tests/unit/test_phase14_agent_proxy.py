from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from api.agent_proxy import (
    AgentProxyHandler,
    FileMetricsCache,
    ProxyConfig,
    VerificationResult,
    WalletRateLimiter,
    anonymized_wallet_id,
    build_paid_agent_event,
    metrics_cache_filename,
    parse_route_policy_body,
    paid_openapi_document,
)


CONFIG = ProxyConfig(
    benchmark_api_base_url="http://benchmark.local",
    verifier_url="https://verifier.local",
    verifier_token="token",
    charge_usdc="0.05",
    supported_payment_networks=["base", "solana"],
    wallet_rate_limit_per_min=60,
)


class TestPhase14AgentProxy(unittest.TestCase):
    def test_paid_openapi_advertises_payment_metadata(self) -> None:
        document = paid_openapi_document(CONFIG)
        operation = document["paths"]["/v1/route-policy"]["post"]

        self.assertEqual(operation["x-payment-info"]["price"]["amount"], "0.05")
        self.assertEqual(operation["x-payment-info"]["price"]["currency"], "USD")
        self.assertIn("402", operation["responses"])
        self.assertEqual(operation["requestBody"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/RoutePolicyRequest")

    def test_request_defaults_and_bounds(self) -> None:
        status_code, payload = parse_route_policy_body({})
        self.assertEqual(status_code, 200)
        self.assertEqual(payload, {"window": "1h", "limit": 3})

        status_code, payload = parse_route_policy_body({"window": "bad", "limit": 3})
        self.assertEqual(status_code, 400)
        self.assertEqual(payload["error"], "bad_request")

        status_code, payload = parse_route_policy_body({"window": "1h", "limit": 11})
        self.assertEqual(status_code, 400)
        self.assertEqual(payload["error"], "bad_request")

    def test_unpaid_request_returns_402_with_payment_required_header(self) -> None:
        handler = _handler(verifier=FixedVerifier(VerificationResult(valid=False, reason="missing_payment_signature")))
        with _server(handler) as server:
            status, headers, body = _post(server.server_port, "/v1/route-policy", {})

        payload = json.loads(body)
        self.assertEqual(status, 402)
        self.assertIn("payment-required", headers)
        self.assertEqual(payload["payment"]["price"]["amount"], "0.05")
        self.assertEqual([item["network"] for item in payload["payment"]["accepts"]], ["base", "solana"])

    def test_invalid_payment_request_returns_402(self) -> None:
        handler = _handler(verifier=FixedVerifier(VerificationResult(valid=False, reason="verifier_rejected")))
        with _server(handler) as server:
            status, _, body = _post(server.server_port, "/v1/route-policy", {}, headers={"PAYMENT-SIGNATURE": "bad"})

        payload = json.loads(body)
        self.assertEqual(status, 402)
        self.assertEqual(payload["reason"], "verifier_rejected")

    def test_valid_paid_request_returns_benchmark_bounded_policy(self) -> None:
        handler = _handler(
            verifier=FixedVerifier(VerificationResult(valid=True, wallet="wallet-1", payment_response={"valid": True})),
            benchmark_client=FixedBenchmarkClient(status=200, payload=_benchmark_payload()),
        )
        with _server(handler) as server:
            status, headers, body = _post(
                server.server_port,
                "/v1/route-policy",
                {"window": "1h", "limit": 1},
                headers={"PAYMENT-SIGNATURE": "paid"},
            )

        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("payment-response", headers)
        self.assertFalse(payload["meta"]["suitable_for_runtime_routing"])
        self.assertEqual(payload["meta"]["payment_status"], "paid")
        self.assertEqual(payload["data"]["candidates"][0]["route_id"], "route-a")
        self.assertFalse(payload["data"]["candidates"][0]["suitable_for_runtime_routing"])

    def test_valid_paid_request_rate_limits_per_wallet(self) -> None:
        handler = _handler(
            verifier=FixedVerifier(VerificationResult(valid=True, wallet="wallet-1")),
            benchmark_client=FixedBenchmarkClient(status=200, payload=_benchmark_payload()),
            rate_limiter=WalletRateLimiter(limit_per_minute=1),
        )
        with _server(handler) as server:
            first_status, _, _ = _post(server.server_port, "/v1/route-policy", {}, headers={"PAYMENT-SIGNATURE": "paid"})
            second_status, _, second_body = _post(server.server_port, "/v1/route-policy", {}, headers={"PAYMENT-SIGNATURE": "paid"})

        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 429)
        self.assertEqual(json.loads(second_body)["error"], "rate_limited")

    def test_upstream_benchmark_failure_returns_503(self) -> None:
        handler = _handler(
            verifier=FixedVerifier(VerificationResult(valid=True, wallet="wallet-1")),
            benchmark_client=FixedBenchmarkClient(status=503, payload={"error": "cache_temporarily_unavailable"}),
        )
        with _server(handler) as server:
            status, _, body = _post(server.server_port, "/v1/route-policy", {}, headers={"PAYMENT-SIGNATURE": "paid"})

        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "benchmark_unavailable")

    def test_paid_event_redacts_payment_and_wallet_material(self) -> None:
        event = build_paid_agent_event(
            config=ProxyConfig(
                **{**CONFIG.__dict__, "wallet_hash_salt": "test-salt", "verifier_token": "secret-token"}
            ),
            outcome="paid_success",
            path="/v1/route-policy",
            status_code=200,
            started_at=0,
            request_body={"window": "1h", "limit": 3, "raw": "must-not-log"},
            verification=VerificationResult(
                valid=True,
                wallet="full-wallet-address",
                payment_response={"valid": True, "network": "solana", "payment_signature": "secret-signature"},
            ),
            wallet="full-wallet-address",
            upstream_status=200,
        )
        encoded = json.dumps(event, sort_keys=True)
        self.assertIn("wallet_", encoded)
        self.assertNotIn("full-wallet-address", encoded)
        self.assertNotIn("secret-token", encoded)
        self.assertNotIn("secret-signature", encoded)
        self.assertNotIn("must-not-log", encoded)
        self.assertEqual(event["payment_network"], "solana")

    def test_proxy_emits_one_event_for_paid_success(self) -> None:
        recorder = RecordingEventRecorder()
        handler = _handler(
            verifier=FixedVerifier(VerificationResult(valid=True, wallet="wallet-1", payment_response={"valid": True})),
            benchmark_client=FixedBenchmarkClient(status=200, payload=_benchmark_payload()),
            event_recorder=recorder,
            config=ProxyConfig(**{**CONFIG.__dict__, "wallet_hash_salt": "test-salt"}),
        )
        with _server(handler) as server:
            status, _, _ = _post(server.server_port, "/v1/route-policy", {}, headers={"PAYMENT-SIGNATURE": "paid"})

        self.assertEqual(status, 200)
        self.assertEqual(len(recorder.events), 1)
        self.assertEqual(recorder.events[0]["outcome"], "paid_success")
        self.assertEqual(recorder.events[0]["wallet_id"], anonymized_wallet_id("wallet-1", "test-salt"))

    def test_proxy_emits_events_for_failure_outcomes(self) -> None:
        scenarios = [
            (
                "bad_request",
                FixedVerifier(VerificationResult(valid=True, wallet="wallet-1")),
                {"window": "bad"},
                None,
                400,
            ),
            (
                "payment_required",
                FixedVerifier(VerificationResult(valid=False, reason="missing_payment_signature")),
                {},
                None,
                402,
            ),
            (
                "payment_rejected",
                FixedVerifier(VerificationResult(valid=False, reason="verifier_rejected")),
                {},
                {"PAYMENT-SIGNATURE": "bad"},
                402,
            ),
            (
                "rate_limited",
                FixedVerifier(VerificationResult(valid=True, wallet="wallet-1")),
                {},
                {"PAYMENT-SIGNATURE": "paid"},
                429,
            ),
            (
                "benchmark_unavailable",
                FixedVerifier(VerificationResult(valid=True, wallet="wallet-1")),
                {},
                {"PAYMENT-SIGNATURE": "paid"},
                503,
            ),
        ]
        for outcome, verifier, body, headers, expected_status in scenarios:
            with self.subTest(outcome=outcome):
                recorder = RecordingEventRecorder()
                rate_limiter = WalletRateLimiter(limit_per_minute=0) if outcome == "rate_limited" else None
                benchmark_status = 503 if outcome == "benchmark_unavailable" else 200
                handler = _handler(
                    verifier=verifier,
                    benchmark_client=FixedBenchmarkClient(status=benchmark_status, payload=_benchmark_payload()),
                    rate_limiter=rate_limiter,
                    event_recorder=recorder,
                    config=ProxyConfig(**{**CONFIG.__dict__, "wallet_hash_salt": "test-salt"}),
                )
                with _server(handler) as server:
                    status, _, _ = _post(server.server_port, "/v1/route-policy", body, headers=headers)
                self.assertEqual(status, expected_status)
                self.assertEqual(len(recorder.events), 1)
                self.assertEqual(recorder.events[0]["outcome"], outcome)

    def test_private_metrics_endpoint_requires_admin_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "meta": {"service": "canopy-agent-proxy", "window": "24h", "data_quality_status": "ready"},
                "data": {"totals": {"paid_success_count": 2}, "breakdowns": {}, "latest_events": []},
            }
            Path(tmpdir, metrics_cache_filename("24h")).write_text(json.dumps(payload), encoding="utf-8")
            config = ProxyConfig(**{**CONFIG.__dict__, "admin_token": "admin", "metrics_cache_dir": tmpdir})
            handler = _handler(verifier=FixedVerifier(VerificationResult(valid=False)), config=config)
            with _server(handler) as server:
                missing_status, _, _ = _get(server.server_port, "/internal/agentcash-metrics?window=24h")
                bad_status, _, _ = _get(
                    server.server_port,
                    "/internal/agentcash-metrics?window=24h",
                    headers={"Authorization": "Bearer wrong"},
                )
                ok_status, _, ok_body = _get(
                    server.server_port,
                    "/internal/agentcash-metrics?window=24h",
                    headers={"Authorization": "Bearer admin"},
                )

        self.assertEqual(missing_status, 403)
        self.assertEqual(bad_status, 403)
        self.assertEqual(ok_status, 200)
        self.assertEqual(json.loads(ok_body)["data"]["totals"]["paid_success_count"], 2)

    def test_private_ops_dashboard_requires_admin_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ProxyConfig(
                **{
                    **CONFIG.__dict__,
                    "admin_token": "admin",
                    "admin_dashboard_slug": "secret-slug",
                    "metrics_cache_dir": tmpdir,
                }
            )
            handler = _handler(verifier=FixedVerifier(VerificationResult(valid=False)), config=config)
            with _server(handler) as server:
                missing_status, _, _ = _get(server.server_port, "/ops/secret-slug")
                ok_status, ok_headers, ok_body = _get(
                    server.server_port,
                    "/ops/secret-slug",
                    headers={"Authorization": "Bearer admin"},
                )

        self.assertEqual(missing_status, 403)
        self.assertEqual(ok_status, 200)
        self.assertIn("text/html", ok_headers["content-type"])
        self.assertIn("Canopy AgentCash Ops", ok_body)


class FixedVerifier:
    def __init__(self, result: VerificationResult) -> None:
        self.result = result

    def verify(self, *, headers: dict[str, str], request_body: dict[str, Any], path: str) -> VerificationResult:
        return self.result


class FixedBenchmarkClient:
    def __init__(self, status: int = 200, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self.payload = payload or _benchmark_payload()

    def dashboard_summary(self, window: str) -> tuple[int, dict[str, Any]]:
        return self.status, self.payload


class RecordingEventRecorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class _server:
    def __init__(self, handler: type[AgentProxyHandler]) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> ThreadingHTTPServer:
        self.thread.start()
        return self.server

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def _handler(
    *,
    verifier: FixedVerifier,
    benchmark_client: FixedBenchmarkClient | None = None,
    rate_limiter: WalletRateLimiter | None = None,
    event_recorder: RecordingEventRecorder | None = None,
    config: ProxyConfig = CONFIG,
) -> type[AgentProxyHandler]:
    return type(
        "TestHandler",
        (AgentProxyHandler,),
        {
            "config": config,
            "verifier": verifier,
            "benchmark_client": benchmark_client or FixedBenchmarkClient(),
            "rate_limiter": rate_limiter or WalletRateLimiter(config.wallet_rate_limit_per_min),
            "event_recorder": event_recorder or RecordingEventRecorder(),
            "metrics_cache": FileMetricsCache(config.metrics_cache_dir),
        },
    )


def _post(
    port: int,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    try:
        connection.request("POST", path, body=json.dumps(body), headers=request_headers)
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, response_headers, response_body
    finally:
        connection.close()


def _get(
    port: int,
    path: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, response_headers, response_body
    finally:
        connection.close()


def _benchmark_payload() -> dict[str, Any]:
    return {
        "meta": {
            "metrics_timestamp": "2026-05-07T00:00:00Z",
            "last_validated_at": "2026-05-07T00:00:00Z",
            "data_quality_status": "bootstrap",
            "x402_signal_status": "unavailable",
        },
        "data": {
            "panels": {
                "observed_effective_cost_leaderboard": [
                    {
                        "route_id": "route-a",
                        "observed_cost_pct": 0.01,
                        "route_share_pct": 50.0,
                        "observed_settlement_rate": 0.99,
                        "data_quality_status": "bootstrap",
                    },
                    {
                        "route_id": "route-b",
                        "observed_cost_pct": 0.02,
                        "route_share_pct": 25.0,
                        "observed_settlement_rate": 0.95,
                        "data_quality_status": "bootstrap",
                    },
                ]
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
