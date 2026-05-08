#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

warn() {
  echo "WARN: $1"
}

echo "Running Canopy Atlas doctor checks..."

command -v python3 >/dev/null 2>&1 || fail "python3 not found"
command -v node >/dev/null 2>&1 || fail "node not found"

[[ -f "AGENTS.md" ]] || fail "missing AGENTS.md"
rg -n "Human-Write-Only|HUMAN-WRITE-ONLY|human-write-only" AGENTS.md >/dev/null 2>&1 || fail "AGENTS.md missing Human-Write-Only marker"
[[ -f "README.md" ]] || fail "missing README.md"
[[ -f "docs/integration-guide.md" ]] || fail "missing docs/integration-guide.md"
[[ -f "docs/data-and-decision-layer-integration.md" ]] || fail "missing data/decision integration guide"
[[ -f "sample_data/solana_evidence_rows.json" ]] || fail "missing sample fixture"

if [[ -n "${SERVICE_ACCOUNT_KEY_PATH:-}" ]]; then
  fail "SERVICE_ACCOUNT_KEY_PATH env var must not be set"
fi

if rg -n "SERVICE_ACCOUNT_KEY_PATH\\s*=" api pipeline sql config tests .github >/dev/null 2>&1; then
  fail "SERVICE_ACCOUNT_KEY_PATH assignment found in source tree"
fi

if [[ -z "${ATLAS_ORCHESTRATOR_TOKEN:-}" ]]; then
  warn "ATLAS_ORCHESTRATOR_TOKEN is not set; /internal/run will fail closed"
fi

python3 -m json.tool sample_data/solana_evidence_rows.json >/dev/null

echo "Doctor checks passed."
