# AGENTS.md - Canopy Atlas Public Contributor Contract

Human-Write-Only: this file defines the public repo operating contract and should be changed only through explicit human-approved edits.

## Scope

Canopy Atlas is a benchmark evidence project for Solana/x402 hackathon work. Agents should preserve the safety boundary: benchmark evidence only, no custody, no payment execution, and no live autonomous routing claim by default.

## Implementation Rules

- Keep `x402` only where it refers to the public protocol or optional paid access behavior.
- Do not introduce private infrastructure names, private service URLs, collaborator names, or real account emails.
- Keep secrets out of the repo.
- Prefer the fixture-backed generic adapter for local development.
- Preserve deterministic event IDs, stable ordering, and idempotent SQL.
- Do not add dependencies without a clear implementation need.

## Validation

Run relevant checks before completion:

```bash
make doctor
make lint-phase0
python3 -m unittest discover -s tests/unit
cd dashboard && npm run build
```

If a check cannot run, report exactly why.
