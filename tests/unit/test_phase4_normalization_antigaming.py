import pathlib
import unittest

from pipeline.adapter.generic_adapter import map_upstream_row_to_raw_event
from pipeline.normalize.normalizer import normalize_raw_event, solana_merge_key
from pipeline.validate.anti_gaming import build_self_transfer_flag, compute_flag_id


ROOT = pathlib.Path(__file__).resolve().parents[2]


def raw_event(**overrides):
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
        "to_address": "receiver",
        "token_address": "mint",
        "token_symbol": "PYUSD",
        "amount_raw": "1000000",
        "decimals": 6,
        "amount_tokens": "1.0",
        "amount_usd_proxy": 1.0,
        "fee_usd_proxy": 0.001,
        "source_path": "fixture:sample_data/solana_evidence_rows.json",
        "decode_version": "fixture-v1",
    }
    row.update(overrides)
    return map_upstream_row_to_raw_event(
        row,
        run_id="run-1",
        ingestion_id="ingest-1",
        default_decode_version="fallback",
        ingested_at="2026-05-06T00:00:00Z",
    )


class TestPhase4NormalizationAntiGaming(unittest.TestCase):
    def test_top_level_instruction_merge_idempotent(self) -> None:
        normalized_a = normalize_raw_event(raw_event(), last_validated_at="2026-05-06T00:00:00Z")
        normalized_b = normalize_raw_event(raw_event(), last_validated_at="2026-05-06T00:00:00Z")
        self.assertEqual(solana_merge_key(normalized_a), solana_merge_key(normalized_b))
        self.assertEqual(solana_merge_key(normalized_a), ("solana", "sig1", 0, False, -1))

    def test_inner_instruction_merge_idempotent(self) -> None:
        normalized = normalize_raw_event(
            raw_event(is_inner=True, inner_instruction_index=2),
            last_validated_at="2026-05-06T00:00:00Z",
        )
        self.assertEqual(solana_merge_key(normalized), ("solana", "sig1", 0, True, 2))

    def test_solana_collision_prevention(self) -> None:
        top_level = normalize_raw_event(raw_event(), last_validated_at="2026-05-06T00:00:00Z")
        inner = normalize_raw_event(
            raw_event(is_inner=True, inner_instruction_index=0),
            last_validated_at="2026-05-06T00:00:00Z",
        )
        self.assertNotEqual(top_level.normalized_payment_id, inner.normalized_payment_id)

    def test_confirmed_memo_signal_sets_x402(self) -> None:
        staged = raw_event(x402_signal_detected=True)
        normalized = normalize_raw_event(staged, last_validated_at="2026-05-06T00:00:00Z")
        self.assertEqual(normalized.protocol_type, "x402_facilitator")

    def test_no_signal_sets_protocol_unknown(self) -> None:
        normalized = normalize_raw_event(raw_event(), last_validated_at="2026-05-06T00:00:00Z")
        self.assertEqual(normalized.protocol_type, "unknown")

    def test_known_address_alone_not_x402(self) -> None:
        normalized = normalize_raw_event(
            raw_event(to_address="known_facilitator_wallet"),
            last_validated_at="2026-05-06T00:00:00Z",
        )
        self.assertEqual(normalized.to_address, "known_facilitator_wallet")
        self.assertEqual(normalized.protocol_type, "unknown")

    def test_fee_status_never_null(self) -> None:
        normalized = normalize_raw_event(raw_event(), last_validated_at="2026-05-06T00:00:00Z")
        self.assertEqual(normalized.network_fee_observation_status, "direct_observed")
        self.assertEqual(normalized.priority_fee_observation_status, "not_observed")
        self.assertEqual(normalized.facilitator_fee_observation_status, "unavailable")

    def test_amount_decode_failure_sets_none(self) -> None:
        normalized = normalize_raw_event(
            raw_event(amount_tokens="not-a-number"),
            last_validated_at="2026-05-06T00:00:00Z",
        )
        self.assertIsNone(normalized.amount_tokens)

    def test_anti_gaming_merge_idempotent(self) -> None:
        flag_a = build_self_transfer_flag(
            route_id="solana_PYUSD_unknown_long_tail",
            chain="solana",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T01:00:00Z",
            tx_count=3,
        )
        flag_b = build_self_transfer_flag(
            route_id="solana_PYUSD_unknown_long_tail",
            chain="solana",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T01:00:00Z",
            tx_count=3,
        )
        self.assertEqual(flag_a.merge_key(), flag_b.merge_key())
        self.assertEqual(flag_a.flag_id, flag_b.flag_id)

    def test_antigaming_flag_id_deterministic(self) -> None:
        flag_id = compute_flag_id(
            "solana_PYUSD_unknown_long_tail",
            "solana",
            "self_transfer",
            "2026-05-06T00:00:00Z",
        )
        self.assertEqual(
            flag_id,
            compute_flag_id(
                "solana_PYUSD_unknown_long_tail",
                "solana",
                "self_transfer",
                "2026-05-06T00:00:00Z",
            ),
        )
        self.assertEqual(len(flag_id), 64)

    def test_no_generate_uuid_in_antigaming_sql(self) -> None:
        sql = (ROOT / "sql" / "validation" / "anti_gaming_flags_merge.sql").read_text(encoding="utf-8")
        self.assertNotIn("GENERATE_UUID", sql.upper())
        self.assertIn("TO_HEX(SHA256(CONCAT", sql)
        self.assertIn("target.route_id = source.route_id", sql)


if __name__ == "__main__":
    unittest.main()
