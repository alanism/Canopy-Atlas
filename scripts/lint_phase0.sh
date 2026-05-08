#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

echo "Running Phase 0 lint guardrails..."

# 1) Public API request path must not import BigQuery clients.
if rg -n "google\\.cloud\\.bigquery|from\\s+google\\.cloud\\s+import\\s+bigquery|BigQueryClient|bigquery\\.Client" api >/dev/null 2>&1; then
  fail "BigQuery import detected in api/"
fi

# 2) Service account key path must not appear in tracked source.
if rg -n "SERVICE_ACCOUNT_KEY_PATH\\s*=" api pipeline sql config >/dev/null 2>&1; then
  fail "SERVICE_ACCOUNT_KEY_PATH assignment detected"
fi

# 3) Health client must not import or instantiate BigQuery.
if [[ -f "pipeline/adapter/upstream_health_client.py" ]] && \
  rg -n "google\\.cloud\\.bigquery|from\\s+google\\.cloud\\s+import\\s+bigquery|bigquery\\.Client" pipeline/adapter/upstream_health_client.py >/dev/null 2>&1; then
  fail "BigQuery usage detected in upstream_health_client.py"
fi

# 4) SQL guardrails for deterministic and bounded logic.
if rg -n "SELECT\\s+\\*" sql pipeline >/dev/null 2>&1; then
  fail "SELECT * detected in sql/ or pipeline/"
fi

if rg -n "GENERATE_UUID\\s*\\(" sql/metrics sql/validation pipeline >/dev/null 2>&1; then
  fail "GENERATE_UUID() detected in deterministic SQL surfaces"
fi

if rg -n "CURRENT_TIMESTAMP\\s*\\(" sql/metrics sql/validation pipeline >/dev/null 2>&1; then
  fail "CURRENT_TIMESTAMP() detected in logical metric SQL surfaces"
fi

# 5) When query helpers exist, they must set maximum_bytes_billed.
if rg -n "\\.query\\s*\\(" pipeline sql >/dev/null 2>&1; then
  if ! rg -n "maximum_bytes_billed" pipeline sql >/dev/null 2>&1; then
    fail "query() usage found without maximum_bytes_billed guardrail"
  fi
fi

# 6) Do not hardcode x402 title claim in dashboard code.
if rg -n "x402 Fee & Route Transparency Dashboard" dashboard api >/dev/null 2>&1; then
  fail "hardcoded public x402 title claim detected"
fi

echo "Phase 0 lint checks passed."
