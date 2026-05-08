# Integration Readiness Review

## Upstream Evidence

The default upstream evidence source is `sample_data/solana_evidence_rows.json`. External sources can implement the generic adapter contract.

Upstream evidence is considered demo-safe only when schema, freshness, and reconciliation gates are explicit.

## Public API

The `/v0/*` endpoints are benchmark-only and cache-first.

Without an external validated data source, deployment posture should be treated as sample mode only.

## Decision Layer

Decision layers can consume route metrics and quality flags for demos, ranking, policy exploration, or risk scoring.

## Product Claims

Canopy Atlas is private-data-free in sample mode and remains not live autonomous routing.
