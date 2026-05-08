# Canopy Atlas Runbook

## Startup

```bash
cp .env.example .env
make doctor
CANOPY_BOOTSTRAP_EMPTY_CACHE=1 python3 -m api.server
cd dashboard && npm ci && npm audit --audit-level=moderate && npm run dev
```

Optional deployed-service check:

```bash
gcloud run services list --project YOUR_PROJECT_ID --region YOUR_REGION
curl -H "Accept: application/json" http://127.0.0.1:8080/v0/status
```

## Test Command

```bash
make lint-phase0
python3 -m unittest discover -s tests/unit
cd dashboard && npm run build
```

For complete operator setup, use `docs/operators-manual.md`. For release readiness, use `docs/deployment-premortem.md`.

## Daily Monitoring

- Check `/healthz`.
- Check `/v0/status`.
- Confirm `runtime_warning` and `data_quality_status` match the deployed data source.
- Review paid proxy metrics only when `AGENTCASH_ADMIN_TOKEN` is configured.

## Alert Response

- Cache unavailable: serve last-known-good snapshots or return 503.
- Upstream stale: keep benchmark fallback copy and avoid validated/runtime claims.
- Token missing: set `ATLAS_ORCHESTRATOR_TOKEN` before calling `/internal/run`.

## Known Failure Modes

- Missing fixture file.
- External adapter returns ambiguous Solana identity.
- Cache backend unavailable.
- Paid proxy verifier not configured.
- BigQuery placeholders not replaced in deployment config.

## Stale-Run Handling

The orchestrator marks old running locks as stale and emits a structured alert before accepting a later run.

## Cache Rollback

Promote only validated payloads. If cache promotion fails, keep the last known good snapshot and report `cache_unavailable`.

## Upstream Evidence Contract Drift

Fail closed when required identity, token, or validation fields are absent. Update `docs/data-and-decision-layer-integration.md` before changing adapter shape.

## Upstream Evidence Health API Recovery

Verify `contract_version=atlas-upstream-health-v1`, `status=ok`, and `suitable_for_runtime_routing=false` before treating external evidence as healthy.

## Label Correction Workflow

Route labels require evidence. Do not convert known addresses into x402 claims without explicit signal support.

## Security Incident Response

Rotate verifier/admin/orchestrator tokens, disable paid proxy endpoints if needed, and inspect logs for leaked payment signatures or wallet addresses.

## Shutdown And Restore

Stop public services, preserve sample fixtures and schema files, then restart with `CANOPY_BOOTSTRAP_EMPTY_CACHE=1` for a safe demo baseline.
