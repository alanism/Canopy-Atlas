# Canopy Atlas

Canopy Atlas is a Solana/x402 hackathon project for turning stablecoin route evidence into benchmark-grade API and dashboard outputs. It ships with a local fixture-backed adapter so judges and contributors can run the project without private infrastructure.

Atlas is not a wallet, custodian, payment processor, or live autonomous routing oracle. It benchmarks route evidence and keeps public responses marked as `"suitable_for_runtime_routing": false` unless a separate production safety plan changes that boundary.

## What It Includes

- Public `/v0/*` benchmark API surfaces.
- React/Vite evidence dashboard.
- Generic upstream evidence adapter with a Solana sample fixture.
- Deterministic normalization, validation, anti-gaming, and rolling metric helpers.
- Optional AgentCash/x402 paid proxy shape for `POST /v1/route-policy`.
- Public docs for connecting data input layers and decision layers.
- Dark Factory methodology artifact: `Alan_Coding_Dark_Factory_AgenticWorkflow_v4_2.pdf`.

## Quickstart

```bash
cp .env.example .env
make doctor
make lint-phase0
python3 -m unittest discover -s tests/unit
```

Run the API with sample payload bootstrap:

```bash
CANOPY_BOOTSTRAP_EMPTY_CACHE=1 python3 -m api.server
```

Run the dashboard:

```bash
cd dashboard
npm ci
npm audit --audit-level=moderate
npm run dev
```

## Repository Map

| Path | Purpose |
|---|---|
| `api/` | Cache-first public API, discovery metadata, internal trigger guard, and optional paid proxy. |
| `pipeline/` | Generic adapter, deterministic event IDs, normalization, validation, metrics, QA, and orchestration helpers. |
| `sample_data/` | Local Solana evidence fixture used by the public adapter. |
| `dashboard/` | React/Vite evidence console and static/proxy server. |
| `config/` | Public sample-mode chain, label, fee, signal, scheduler, and ingestion config. |
| `sql/` | BigQuery-compatible schema, metric, and validation SQL templates. |
| `tests/unit/` | Phase-oriented tests for the public build. |
| `docs/` | Integration, runbook, monitoring, and adapter connection docs. |
| `deploy/` | Placeholder Cloud Run service separation contract. |

## Data And Decision Layer Extension

The default adapter reads `sample_data/solana_evidence_rows.json`. To connect your own source, implement a `fetch_rows(chain, token_symbol, limit)` method and pass it to `GenericEvidenceAdapter`.

See `docs/data-and-decision-layer-integration.md` for the row shape, adapter contract, and decision-layer handoff guidance.

Operators should start with `docs/operators-manual.md`, then use `docs/deployment-premortem.md` before exposing Cloud Run, BigQuery, AgentCash, or paid upstream provider integrations.

## x402 Boundary

Atlas keeps x402 as public protocol terminology. It does not claim live route execution. The optional paid proxy can charge for API access through AgentCash/x402 when verifier credentials are configured, but it does not execute downstream payments or prove resource delivery.

## Security

Copy `.env.example` and supply secrets locally. Do not commit verifier tokens, admin tokens, wallet keys, service account keys, or production dataset identifiers.

`/internal/run` is disabled unless `ATLAS_ORCHESTRATOR_TOKEN` is configured.

## License

MIT. See `LICENSE`.
