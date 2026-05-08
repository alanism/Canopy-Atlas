# Deployment Premortem

Use this checklist before showing Canopy Atlas to judges, contributors, or operators.

## Release Readiness

- `make doctor` passes.
- `make lint-phase0` passes.
- `python3 -m unittest discover -s tests/unit` passes.
- `cd dashboard && npm ci && npm audit --audit-level=moderate && npm run build` passes.
- Private-term grep gates pass.
- `.env.example` contains placeholders only.
- `dashboard/package-lock.json` is tracked.

## Secrets And Access

- No verifier tokens, wallet keys, service account keys, private URLs, production project IDs, or real account emails are committed.
- `ATLAS_ORCHESTRATOR_TOKEN` is generated per environment and stored outside git.
- `AGENTCASH_VERIFIER_TOKEN`, `AGENTCASH_ADMIN_TOKEN`, merchant addresses, and `WALLET_HASH_SALT` are stored outside git.
- API service account has no BigQuery write role.
- Pipeline service account has only the BigQuery permissions needed for schema, staging, and metrics jobs.

## BigQuery

- `YOUR_PROJECT_ID` and `YOUR_DATASET` have been replaced only in local/cloud deployment config.
- Dataset region matches `BQ_REGION`.
- `BQ_MAX_BYTES_BILLED_INCREMENTAL` and `BQ_MAX_BYTES_BILLED_BACKFILL` are set.
- Schema apply is run idempotently.
- Backfill jobs are dry-run checked before execution.

## AgentCash Paid Proxy

- Paid proxy is optional and separate from free `/v0/*` endpoints.
- AgentCash verifier URL and token are configured only in the paid proxy environment.
- `POST /v1/route-policy` returns 402 without a valid payment signature.
- Admin metrics require `AGENTCASH_ADMIN_TOKEN`.
- Payment signatures and wallet values are redacted or hashed in emitted metrics.

## Upstream Evidence Provider

- Sample fixture mode works before external providers are connected.
- External provider rows satisfy the generic adapter contract.
- Project-DG compatible paid upstream evidence service (Coming Soon) is treated as a provider, not as repo-owned infrastructure.
- Contract drift fails closed and leaves sample mode available.

## Cloud Run

- `canopy-atlas-api`, `canopy-atlas-dashboard`, and `canopy-agent-proxy` are separate services.
- Dashboard API base URL points at the intended API service.
- `/internal/run` is not publicly callable without the configured bearer token and platform boundary.
- Scheduler targets the private orchestrator path only.

## User Experience

- Dashboard renders a clear API-unreachable state when `/v0/dashboard-summary` is unavailable.
- README quickstart is enough to run sample mode.
- Operator manual covers local setup, Cloud Run, BigQuery, AgentCash, and troubleshooting.
- Integration docs state that Atlas is benchmark evidence, not custody, settlement, or live autonomous routing.

## Rollback

- Disable scheduler triggers.
- Revert Cloud Run traffic to the previous revision.
- Serve sample mode or last known good cache.
- Rotate AgentCash, admin, orchestrator, and upstream provider tokens.
- Stop BigQuery writes before replaying jobs.

## Cost Controls

- BigQuery max bytes billed settings are enforced.
- Cloud Run min instances match demo needs.
- Paid proxy and admin metrics cache paths are bounded.
- Backfills are run only with explicit operator approval.
