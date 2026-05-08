# Canopy Atlas Operator Manual

This manual is for operators who want to run Canopy Atlas from local sample mode through a Cloud Run + BigQuery deployment. Canopy Atlas publishes benchmark evidence only. It is not custody, payment execution, settlement, or live autonomous routing.

No real secrets belong in this repository. Put tokens, wallet material, verifier credentials, service account bindings, and production dataset identifiers in local environment files or your cloud secret manager.

## 1. Local Sample Mode

Use sample mode first. It proves the API, dashboard, adapter contract, and tests without BigQuery, AgentCash, or any paid upstream provider.

```bash
cp .env.example .env
make doctor
make lint-phase0
python3 -m unittest discover -s tests/unit
CANOPY_BOOTSTRAP_EMPTY_CACHE=1 python3 -m api.server
```

In another shell:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/v0/status
curl "http://127.0.0.1:8080/v0/dashboard-summary?window=1h"
```

Run the dashboard:

```bash
cd dashboard
npm ci
npm audit --audit-level=moderate
npm run dev
```

Healthy sample mode shows a reachable `/v0/dashboard-summary` payload, a dashboard state instead of a blank screen, and benchmark metadata that remains unsuitable for runtime routing.

## 2. Required Accounts And Services

BigQuery is the warehouse target for schema and metric SQL. Create a project and dataset, then replace `YOUR_PROJECT_ID` and `YOUR_DATASET` only in your local deployment config.

AgentCash is optional. Use it only when you want the paid `POST /v1/route-policy` proxy. Configure verifier credentials and merchant addresses outside the repo:

- `AGENTCASH_VERIFIER_URL`
- `AGENTCASH_VERIFIER_TOKEN`
- `AGENTCASH_MERCHANT_ADDRESS_BASE`
- `AGENTCASH_MERCHANT_ADDRESS_SOLANA`
- `AGENTCASH_ADMIN_TOKEN`
- `WALLET_HASH_SALT`

Project-DG compatible paid upstream evidence service (Coming Soon) is an optional provider category. Treat it as a paid upstream evidence source that must satisfy the generic adapter contract. Do not copy provider-specific contracts, private URLs, account names, or privileged validation logic into this repository.

## 3. Environment Variables

Minimum local sample mode:

- `CANOPY_BOOTSTRAP_EMPTY_CACHE=1`
- `CANOPY_DASHBOARD_API_BASE_URL=http://127.0.0.1:8080`

Private orchestration:

- `ATLAS_ORCHESTRATOR_TOKEN` must be set before calling `/internal/run`.
- Missing `ATLAS_ORCHESTRATOR_TOKEN` is a healthy fail-closed state.

BigQuery:

- `GCP_PROJECT_ID=YOUR_PROJECT_ID`
- `BQ_DATASET=YOUR_DATASET`
- `BQ_REGION=US`
- `BQ_MAX_BYTES_BILLED_INCREMENTAL`
- `BQ_MAX_BYTES_BILLED_BACKFILL`

Paid proxy:

- `CANOPY_BENCHMARK_API_BASE_URL`
- `AGENTCASH_VERIFIER_URL`
- `AGENTCASH_VERIFIER_TOKEN`
- `CHARGE_USDC`
- `SUPPORTED_PAYMENT_NETWORKS`
- `AGENTCASH_ADMIN_TOKEN`

## 4. BigQuery Setup

Create the dataset and apply `sql/schema/canopy_atlas_staging_tables.sql` through the existing schema helper or your deployment runner. Keep SQL placeholders templated until deployment time:

```text
{project} -> YOUR_PROJECT_ID
{dataset} -> YOUR_DATASET
```

The API service account must not hold BigQuery write roles. Pipeline jobs may hold the narrow BigQuery permissions needed to apply schema and write staging or metric tables.

## 5. Cloud Run Deployment Shape

Deploy separate services:

- `canopy-atlas-api` for free `/v0/*` benchmark endpoints.
- `canopy-atlas-dashboard` for the React static dashboard.
- `canopy-agent-proxy` for optional paid AgentCash/x402 route-policy access.

Keep the orchestrator trigger private. `/internal/run` must require `ATLAS_ORCHESTRATOR_TOKEN` or an equivalent Cloud Run/IAM boundary in addition to app-level fail-closed behavior.

## 6. Connecting Data Inputs

External sources should implement:

```python
fetch_rows(chain: str, token_symbol: str, limit: int = 100) -> list[dict]
```

Valid sources include BigQuery tables, JSON exports, indexer APIs, warehouse views, or a paid upstream evidence provider. Required row fields are documented in `docs/data-and-decision-layer-integration.md`.

## 7. Operating Checks

Before a public demo:

- `make doctor`
- `make lint-phase0`
- `python3 -m unittest discover -s tests/unit`
- `cd dashboard && npm ci && npm audit --audit-level=moderate && npm run build`
- `curl /healthz`
- `curl /v0/status`
- `curl /v0/dashboard-summary?window=1h`

Healthy operation means the API responds, dashboard renders, cache metadata is current for the selected mode, and paid proxy metrics are visible only with `AGENTCASH_ADMIN_TOKEN`.

## 8. Troubleshooting

- API unreachable: confirm `CANOPY_DASHBOARD_API_BASE_URL`, API port, and `/healthz`.
- Empty dashboard: start the API with `CANOPY_BOOTSTRAP_EMPTY_CACHE=1` or promote a validated cache payload.
- 503 on `/internal/run`: configure `ATLAS_ORCHESTRATOR_TOKEN`.
- 402 on `POST /v1/route-policy`: confirm AgentCash payment signature and verifier credentials.
- BigQuery cost risk: confirm max bytes billed settings before backfill.
- Upstream contract drift: fail closed, keep sample mode online, and update the adapter contract docs before changing row shape.

## 9. Rollback

Disable scheduler triggers, keep `/v0/*` in sample mode, preserve the last known good cache snapshot, and rotate any exposed AgentCash or orchestrator tokens. For BigQuery mistakes, stop writes before replaying schema or metric jobs.
