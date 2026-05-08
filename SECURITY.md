# Security Policy

## Supported Surface

This public repo supports local sample-mode development and hackathon evaluation. Production deployment requires a separate security review.

## Secrets

Never commit:

- verifier tokens
- admin tokens
- wallet private keys
- service account keys
- production project IDs or dataset names
- raw payment signatures or full payer wallet addresses

Use `.env.example` as a placeholder template only.

## Internal Trigger

`/internal/run` fails closed unless `ATLAS_ORCHESTRATOR_TOKEN` is configured. Use a local random token for development and rotate it for any deployment.

## Paid Proxy

The AgentCash/x402 paid proxy is optional. It requires verifier credentials supplied out of repo and should redact wallet/payment material in logs.

## Reporting

Open an issue with a minimal reproduction for non-sensitive reports. For sensitive reports, contact the repository maintainer through the competition submission channel.
