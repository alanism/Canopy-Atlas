# Monitoring And Alerts

## Grouping

- Redis Outage: `cache_unavailable`, `api_503`, `cache_promotion_failed`
- Upstream Evidence Stale: `upstream_health_non_ok`, `upstream_freshness_exceeded`, `upstream_reconciliation_stale`
- RPC Outage: `rpc_freshness_lag`, `validation_failure`, `cache_stale`, `pipeline_stale`

## Outcome Metrics

- `dashboard_summary_requests`
- `methodology_page_views`
- `api_access_cta_clicks`
- `correction_submissions`
- `serious_api_access_requests`

The API exposes local counters at `/internal/outcome-metrics`.
