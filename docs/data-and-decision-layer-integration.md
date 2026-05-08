# Data And Decision Layer Integration

Canopy Atlas is intentionally adapter-based. Teams can connect a data input layer or a decision layer without changing the public `/v0/*` API.

## Evidence Row Shape

An upstream evidence row should include:

- `chain`
- Solana identity: `signature`, `instruction_index`, `is_inner`, `inner_instruction_index`
- EVM identity when applicable: `transaction_hash`, `log_index`
- `block_timestamp`, `block_date`, `block_number`
- `from_address`, `to_address`
- `token_symbol`, `token_address`, `amount_raw`, `decimals`, `amount_tokens`
- optional `amount_usd_proxy`, `fee_usd_proxy`
- optional route labels such as `route_id`, `protocol_type`, `x402_signal_status`
- upstream validation fields such as `upstream_match_rate`, `upstream_last_validated_at`, `upstream_validation_status`

## Adapter Contract

Implement an object compatible with:

```python
fetch_rows(chain: str, token_symbol: str, limit: int = 100) -> list[dict]
```

Pass it into `GenericEvidenceAdapter(source)` to reuse deterministic staging, normalization, validation, and metrics helpers.

## Supported Inputs

Reasonable sources include:

- BigQuery or another warehouse
- JSON export from an indexer
- API response from a validator service
- local fixture data for demos
- chain indexer or RPC-derived sample rows
- paid upstream evidence providers that satisfy this contract

## Decision Layer Outputs

A decision layer can consume route metrics, quality status, runtime warnings, and x402 signal posture. Keep policy engines separate from Atlas unless a production plan explicitly approves live routing.

See `docs/operators-manual.md` for BigQuery, AgentCash, Cloud Run, and paid upstream provider setup. Provider-specific credentials and private contracts must stay out of the repository.

## Limits

Canopy Atlas benchmarks evidence. It does not custody funds, execute payments, settle merchant balances, guarantee delivery, or authorize autonomous production routing by default.
