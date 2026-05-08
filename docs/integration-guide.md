# Canopy Atlas Integration Guide

Canopy Atlas exposes benchmark-grade stablecoin route evidence for Solana/x402 experiments. It is not a wallet, payment processor, live routing oracle, custody layer, or autonomous route executor. Public `/v0/*` endpoints are free, read-only, cache-first, and marked with `"suitable_for_runtime_routing": false`.

Canopy Atlas is not live autonomous routing.

## Public API

- `GET /v0`
- `GET /v0/dashboard-summary?window=1h`
- `GET /v0/routes`
- `GET /v0/fees`
- `GET /v0/route-share`
- `GET /v0/reliability`
- `GET /v0/status`
- `GET /v0/methodology`
- `GET /openapi.json`
- `GET /llms.txt`

Public endpoints reject manual refresh parameters such as `refresh=1`; request-path handlers must read cache or fixture-backed payloads only.

## Paid Agent Proxy

`POST /v1/route-policy` is optional and requires real verifier credentials supplied through environment variables. The paid response is benchmark context for agents; it does not execute a payment route or prove resource delivery.

## Local Sample Mode

The default public adapter reads `sample_data/solana_evidence_rows.json`. This lets judges run the API, dashboard, and tests without warehouse credentials or private infrastructure.

## Safety Envelope

Responses preserve:

```json
{
  "freshness_tier": "benchmark",
  "suitable_for_runtime_routing": false,
  "x402_signal_status": "unavailable"
}
```

Decision layers may consume Atlas outputs for demos, policy exploration, or ranking experiments, but production routing requires an explicit external safety gate.
