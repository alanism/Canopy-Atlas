import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pipeline.adapter.generic_adapter import (
    GenericAdapterError,
    GenericEvidenceAdapter,
    build_adapter_staging_rows,
    get_signal_fetch_candidates,
    map_upstream_row_to_raw_event,
    parse_chain_token_pairs,
    require_adapter_mode,
    validate_raw_mode_bounds,
)


def sample_upstream_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "chain": "solana",
        "block_timestamp": "2026-04-28T23:59:58Z",
        "block_date": "2026-04-28",
        "block_number": 123,
        "transaction_hash": "sig1",
        "log_index": 0,
        "signature": "sig1",
        "instruction_index": 0,
        "is_inner": False,
        "inner_instruction_index": None,
        "from_address": "payer",
        "to_address": "known_facilitator_wallet",
        "token_address": "mint",
        "token_symbol": "PYUSD",
        "amount_raw": "1000000",
        "decimals": 6,
        "amount_tokens": "1.0",
        "amount_token": "1.0",
        "amount_usd_proxy": 1.0,
        "fee_usd_proxy": 0.001,
        "source_path": "fixture:sample_data/solana_evidence_rows.json",
        "decode_version": "fixture-v1",
        "source_table": "upstream_evidence_contract_v1",
        "ingest_run_id": None,
    }
    row.update(overrides)
    return row


class FakeSource:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def fetch_rows(self, *, chain: str, token_symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        self.calls.append({"chain": chain, "token_symbol": token_symbol, "limit": limit})
        return self.rows


class TestPhase3UpstreamAdapter(unittest.TestCase):
    def test_phase3_skips_raw_when_adapter_mode(self) -> None:
        require_adapter_mode({"ingestion_mode": "adapter"})
        with self.assertRaises(GenericAdapterError):
            require_adapter_mode({"ingestion_mode": "raw"})

    def test_adapter_maps_required_fields(self) -> None:
        staged = map_upstream_row_to_raw_event(
            sample_upstream_row(),
            run_id="run-1",
            ingestion_id="ingest-1",
            default_decode_version="fallback",
            ingested_at="2026-05-06T00:00:00Z",
        )
        self.assertEqual(staged.raw_event_id, "solana_sig1_0_-1")
        self.assertEqual(staged.ingestion_id, "ingest-1")
        self.assertEqual(staged.run_id, "run-1")
        self.assertEqual(staged.source_path, "fixture:sample_data/solana_evidence_rows.json")
        self.assertEqual(staged.decode_version, "fixture-v1")
        self.assertEqual(staged.block_date, "2026-04-28")
        self.assertFalse(staged.is_inner)
        self.assertFalse(staged.x402_signal_detected)

    def test_adapter_plus_signal_fetch_uses_candidate_transactions_only(self) -> None:
        staged = [
            map_upstream_row_to_raw_event(
                sample_upstream_row(signature="sig1"),
                run_id="run-1",
                ingestion_id="ingest-1",
                default_decode_version="fallback",
            )
        ]
        candidates = get_signal_fetch_candidates(staged)
        self.assertEqual(candidates, [{"chain": "solana", "signature": "sig1", "transaction_hash": "sig1", "raw_event_id": "solana_sig1_0_-1"}])

    def test_raw_mode_requires_explicit_slot_bounds(self) -> None:
        with self.assertRaises(GenericAdapterError):
            validate_raw_mode_bounds()
        with self.assertRaises(GenericAdapterError):
            validate_raw_mode_bounds(start_slot=10, end_slot=10)
        validate_raw_mode_bounds(start_slot=10, end_slot=11)

    def test_upstream_valid_transfer_but_missing_signal_sets_unknown(self) -> None:
        staged = map_upstream_row_to_raw_event(
            sample_upstream_row(),
            run_id="run-1",
            ingestion_id="ingest-1",
            default_decode_version="fallback",
        )
        self.assertEqual(staged.raw_payload["protocol_type"], "unknown")
        self.assertEqual(staged.raw_payload["x402_signal_status"], "unavailable")
        self.assertFalse(staged.x402_signal_detected)

    def test_known_address_alone_not_x402(self) -> None:
        staged = map_upstream_row_to_raw_event(
            sample_upstream_row(to_address="known_facilitator_wallet"),
            run_id="run-1",
            ingestion_id="ingest-1",
            default_decode_version="fallback",
        )
        self.assertEqual(staged.raw_payload["to_address"], "known_facilitator_wallet")
        self.assertFalse(staged.x402_signal_detected)

    def test_build_adapter_staging_rows_obeys_ingestion_mode_and_token_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mode_path = root / "ingestion_mode.json"
            chains_path = root / "chains.yaml"
            mode_path.write_text(json.dumps({"ingestion_mode": "adapter"}), encoding="utf-8")
            chains_path.write_text(
                "v0_targets:\n"
                "  - chain: solana\n"
                "    token_symbol: PYUSD\n",
                encoding="utf-8",
            )
            fake_source = FakeSource([sample_upstream_row()])
            staged_rows = build_adapter_staging_rows(
                fake_source,
                chain="solana",
                token_symbol="PYUSD",
                run_id="run-1",
                ingestion_id="ingest-1",
                decode_version="fallback",
                mode_path=mode_path,
                chains_path=chains_path,
            )
            self.assertEqual(len(staged_rows), 1)
            self.assertEqual(fake_source.calls[0]["token_symbol"], "PYUSD")

    def test_chain_token_parser_handles_comments_quotes_and_reordered_keys(self) -> None:
        content = (
            "v0_targets:\n"
            "  - token_symbol: \"PYUSD\" # sample fixture token\n"
            "    chain: solana\n"
            "  - chain: base\n"
            "    token_symbol: 'USDC'\n"
        )
        self.assertEqual(parse_chain_token_pairs(content), {("solana", "PYUSD"), ("base", "USDC")})

    def test_default_fixture_source_loads_sample_rows(self) -> None:
        staged_rows = GenericEvidenceAdapter().build_staging_rows(
            chain="solana",
            token_symbol="PYUSD",
            run_id="run-1",
            ingestion_id="ingest-1",
            decode_version="fallback",
            limit=10,
        )
        self.assertGreaterEqual(len(staged_rows), 1)


if __name__ == "__main__":
    unittest.main()
