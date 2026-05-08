"""Agent discovery payloads for Canopy Atlas public benchmark endpoints."""

from __future__ import annotations

from typing import Any

API_VERSION = "0.1.0"
SOLANA_MAINNET_CAIP2 = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
SUPPORTED_WINDOWS = ["15m", "1h", "24h", "7d"]
PREFERRED_PAID_PROXY = {
    "service": "canopy-agent-proxy",
    "openapi": "/openapi.json",
    "agent_guidance": "/llms.txt",
    "endpoint": "POST /v1/route-policy",
    "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
    "payment_networks": ["base", "solana"],
}

AGENT_GUIDANCE = """# Canopy Atlas Agent Guide

Canopy Atlas exposes benchmark-grade stablecoin route evidence for agents and developers.
It is not a wallet, payment processor, live routing oracle, or autonomous routing service.

Paid-first start:
- Discover the paid proxy OpenAPI for canopy-agent-proxy.
- Call POST /v1/route-policy through AgentCash for the $0.05 benchmark route-policy interaction.

Free benchmark fallback:
- GET /v0/status
- GET /v0/methodology
- GET /v0/dashboard-summary?window=1h
- GET /openapi.json

Rules for agents:
- Treat every /v0 response as benchmark evidence only.
- Do not use Canopy output for live autonomous route selection when suitable_for_runtime_routing is false.
- Respect runtime_warning, data_quality_status, metrics_timestamp, last_validated_at, and x402_signal_status.
- Public /v0 endpoints remain free, read-only, cache-first, and non-payable.
- Paid AgentCash interactions belong to canopy-agent-proxy, not the /v0 benchmark API.
- Canopy showcases Solana route-intelligence evidence now, but benchmark responses do not execute payments or routes.

Preferred paid endpoint: POST /v1/route-policy on canopy-agent-proxy.
"""


def agent_guidance_text() -> str:
    return AGENT_GUIDANCE


def endpoint_index() -> dict[str, Any]:
    return {
        "meta": {
            "api_version": API_VERSION,
            "freshness_tier": "benchmark",
            "suitable_for_runtime_routing": False,
            "payment_status": "not_payable",
            "discovery": {
                "openapi": "/openapi.json",
                "agent_guidance": ["/llms.txt", "/agents.txt"],
            },
            "preferred_paid_proxy": PREFERRED_PAID_PROXY,
        },
        "data": {
            "purpose": "Benchmark-grade route evidence for AI agents and developers.",
            "content_type": "application/json",
            "supported_windows": SUPPORTED_WINDOWS,
            "solana_showcase": {
                "network": "Solana",
                "caip2": SOLANA_MAINNET_CAIP2,
                "status": "benchmark_evidence_showcase",
                "payment_acceptance": "not_currently_accepted",
                "note": "Canopy analyzes Solana route evidence but does not currently accept or execute payments.",
            },
            "endpoints": [
                _endpoint(
                    path="/v0/dashboard-summary",
                    summary="Dashboard-ready benchmark panel payload.",
                    query={"window": SUPPORTED_WINDOWS},
                ),
                _endpoint(path="/v0/routes", summary="Known benchmark routes from cache."),
                _endpoint(path="/v0/fees", summary="Observed effective cost metrics from cache."),
                _endpoint(path="/v0/route-share", summary="Volume-weighted route share metrics from cache."),
                _endpoint(path="/v0/reliability", summary="Observed settlement health metrics from cache."),
                _endpoint(path="/v0/status", summary="Cache, validation, quality, and signal status."),
                _endpoint(path="/v0/methodology", summary="Machine-readable methodology flags."),
                _endpoint(path="/v0", summary="Agent endpoint index and safety rules."),
            ],
            "safety_rules": [
                "Do not use Canopy Atlas for live autonomous route selection.",
                "Do not add refresh=1; public refresh is intentionally blocked.",
                "Treat Unknown / Decentralized Long Tail as unlabeled observed volume.",
                "Respect runtime_warning, data_quality_status, and last_validated_at.",
            ],
            "paid_agent_proxy": {
                "service": "canopy-agent-proxy",
                "endpoint": "POST /v1/route-policy",
                "status": "paid_first_dual_mode",
                "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
                "payment_networks": ["base", "solana"],
                "note": "Use the paid proxy for AgentCash interactions. Keep /v0 benchmark endpoints free and non-payable for compatibility.",
            },
        },
    }


def openapi_document() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Canopy Atlas Benchmark API",
            "version": API_VERSION,
            "description": (
                "Free, read-only benchmark endpoints for stablecoin route cost, route share, "
                "and observed settlement health. Current v0 endpoints are non-payable and not "
                "suitable for live autonomous routing. AgentCash paid interactions should use "
                "the separate canopy-agent-proxy POST /v1/route-policy endpoint."
            ),
            "x-guidance": (
                "Paid-first agents should discover canopy-agent-proxy and call POST /v1/route-policy "
                "through AgentCash for the $0.05 benchmark route-policy interaction. These /v0 "
                "endpoints remain free benchmark fallback surfaces. Treat all /v0 responses as "
                "benchmark-grade evidence only and do not use them for live autonomous route execution."
            ),
            "x-preferred-paid-proxy": PREFERRED_PAID_PROXY,
        },
        "servers": [{"url": "/", "description": "Current origin"}],
        "tags": [
            {"name": "Discovery", "description": "Agent discovery and endpoint index."},
            {"name": "Benchmark", "description": "Free benchmark-grade route evidence."},
        ],
        "paths": {
            "/v0": {
                "get": {
                    "operationId": "getEndpointIndex",
                    "summary": "Get agent endpoint index",
                    "tags": ["Discovery"],
                    "responses": {"200": _json_response("Endpoint index", "EndpointIndex")},
                }
            },
            "/v0/dashboard-summary": {
                "get": {
                    "operationId": "getDashboardSummary",
                    "summary": "Get dashboard benchmark summary",
                    "tags": ["Benchmark"],
                    "parameters": [
                        {
                            "name": "window",
                            "in": "query",
                            "required": False,
                            "description": "Benchmark aggregation window.",
                            "schema": {"type": "string", "enum": SUPPORTED_WINDOWS, "default": "1h"},
                        }
                    ],
                    "responses": {
                        "200": _json_response("Dashboard summary payload", "DashboardSummaryEnvelope"),
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "503": {"$ref": "#/components/responses/CacheUnavailable"},
                    },
                }
            },
            "/v0/routes": _cached_benchmark_path("getRoutes", "Get benchmark routes"),
            "/v0/fees": _cached_benchmark_path("getFees", "Get observed fee metrics"),
            "/v0/route-share": _cached_benchmark_path("getRouteShare", "Get route share metrics"),
            "/v0/reliability": _cached_benchmark_path("getReliability", "Get observed settlement health metrics"),
            "/v0/status": _cached_benchmark_path("getStatus", "Get benchmark status"),
            "/v0/methodology": {
                "get": {
                    "operationId": "getMethodology",
                    "summary": "Get methodology flags",
                    "tags": ["Benchmark"],
                    "responses": {"200": _json_response("Methodology payload", "BenchmarkEnvelope")},
                }
            },
        },
        "components": {
            "schemas": {
                "BenchmarkMeta": {
                    "type": "object",
                    "properties": {
                        "cache_generation_timestamp": {"type": ["string", "null"]},
                        "metrics_timestamp": {"type": ["string", "null"]},
                        "data_window_start": {"type": ["string", "null"]},
                        "data_window_end": {"type": ["string", "null"]},
                        "last_validated_at": {"type": ["string", "null"]},
                        "data_quality_status": {"type": "string"},
                        "labeled_volume_pct": {"type": "number"},
                        "long_tail_volume_pct": {"type": "number"},
                        "methodology_version": {"type": "string"},
                        "freshness_tier": {"type": "string", "const": "benchmark"},
                        "suitable_for_runtime_routing": {"type": "boolean", "const": False},
                        "runtime_warning": {"type": ["string", "null"]},
                        "x402_signal_status": {"type": "string"},
                        "x402_signal_detected": {"type": "boolean"},
                        "dashboard_title": {"type": "string"},
                    },
                    "required": [
                        "freshness_tier",
                        "suitable_for_runtime_routing",
                        "x402_signal_status",
                        "dashboard_title",
                    ],
                    "additionalProperties": True,
                },
                "BenchmarkEnvelope": {
                    "type": "object",
                    "properties": {
                        "meta": {"$ref": "#/components/schemas/BenchmarkMeta"},
                        "data": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["meta", "data"],
                },
                "DashboardRow": {
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string"},
                        "route_share_pct": {"type": "number"},
                        "observed_cost_pct": {"type": "number"},
                        "observed_settlement_rate": {"type": "number"},
                        "data_quality_status": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "DashboardPanels": {
                    "type": "object",
                    "properties": {
                        "observed_effective_cost_leaderboard": _row_array_schema(),
                        "volume_weighted_route_share": _row_array_schema(),
                        "observed_settlement_health_x_cost": _row_array_schema(),
                        "under_review_routes": _row_array_schema(),
                    },
                    "required": [
                        "observed_effective_cost_leaderboard",
                        "volume_weighted_route_share",
                        "observed_settlement_health_x_cost",
                        "under_review_routes",
                    ],
                },
                "DashboardSummaryEnvelope": {
                    "type": "object",
                    "properties": {
                        "meta": {"$ref": "#/components/schemas/BenchmarkMeta"},
                        "data": {
                            "type": "object",
                            "properties": {"panels": {"$ref": "#/components/schemas/DashboardPanels"}},
                            "required": ["panels"],
                        },
                    },
                    "required": ["meta", "data"],
                },
                "EndpointIndex": {
                    "type": "object",
                    "properties": {
                        "meta": {"type": "object", "additionalProperties": True},
                        "data": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["meta", "data"],
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["error"],
                },
            },
            "responses": {
                "BadRequest": _error_response("Bad request"),
                "CacheUnavailable": _error_response("Cache temporarily unavailable"),
            },
        },
    }


def _endpoint(path: str, summary: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "path": path,
        "methods": ["GET"],
        "summary": summary,
        "content_type": "application/json",
        "freshness_semantics": "cache_or_last_known_good_snapshot",
        "payment_status": "not_payable",
        "suitable_for_runtime_routing": False,
        "query": query or {},
    }


def _cached_benchmark_path(operation_id: str, summary: str) -> dict[str, Any]:
    return {
        "get": {
            "operationId": operation_id,
            "summary": summary,
            "tags": ["Benchmark"],
            "responses": {
                "200": _json_response("Benchmark payload", "BenchmarkEnvelope"),
                "503": {"$ref": "#/components/responses/CacheUnavailable"},
            },
        }
    }


def _json_response(description: str, schema_name: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}},
        },
    }


def _error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


def _row_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"$ref": "#/components/schemas/DashboardRow"}}
