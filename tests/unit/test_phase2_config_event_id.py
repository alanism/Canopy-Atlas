import pathlib
import unittest

from pipeline.ingest.solana_event_id import EventIdError, compute_raw_event_id, compute_solana_raw_event_id


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestPhase2ConfigAndEventId(unittest.TestCase):
    def test_top_level_instruction_fallback(self) -> None:
        event_id = compute_solana_raw_event_id(
            {
                "signature": "sig1",
                "instruction_index": 3,
                "is_inner": False,
                "inner_instruction_index": None,
            }
        )
        self.assertEqual(event_id, "solana_sig1_3_-1")

    def test_inner_instruction_parsing(self) -> None:
        event_id = compute_solana_raw_event_id(
            {
                "signature": "sig1",
                "instruction_index": 3,
                "is_inner": True,
                "inner_instruction_index": 0,
            }
        )
        self.assertEqual(event_id, "solana_sig1_3_0")

    def test_solana_collision_prevention(self) -> None:
        top_level = compute_solana_raw_event_id(
            {
                "signature": "sig1",
                "instruction_index": 3,
                "is_inner": False,
                "inner_instruction_index": None,
            }
        )
        inner = compute_solana_raw_event_id(
            {
                "signature": "sig1",
                "instruction_index": 3,
                "is_inner": True,
                "inner_instruction_index": 0,
            }
        )
        self.assertNotEqual(top_level, inner)

    def test_solana_null_inner_index_does_not_duplicate(self) -> None:
        with self.assertRaises(EventIdError):
            compute_solana_raw_event_id(
                {
                    "signature": "sig1",
                    "instruction_index": 3,
                    "is_inner": True,
                    "inner_instruction_index": None,
                }
            )

    def test_evm_vs_svm_key_enforcement(self) -> None:
        with self.assertRaises(EventIdError):
            compute_raw_event_id(
                "solana",
                {
                    "signature": "sig1",
                    "instruction_index": 3,
                    "is_inner": False,
                    "inner_instruction_index": None,
                    "transaction_hash": "0xabc",
                    "log_index": 1,
                },
            )

        evm_id = compute_raw_event_id("ethereum", {"transaction_hash": "0xabc", "log_index": 1})
        self.assertEqual(len(evm_id), 64)

    def test_empty_x402_signal_config_sets_unavailable(self) -> None:
        signals = (ROOT / "config" / "x402_signals.yaml").read_text(encoding="utf-8")
        self.assertIn("x402_signal_source_available: false", signals)
        self.assertIn("protocol_type_fallback: unknown", signals)
        self.assertIn("x402_signal_status: unavailable", signals)
        self.assertIn("dashboard_title_fallback: Observed Stablecoin Route Benchmark", signals)

    def test_chains_yaml_parseable_and_matches_v0_target(self) -> None:
        chains = (ROOT / "config" / "chains.yaml").read_text(encoding="utf-8")
        for expected in [
            "chain: ethereum",
            "chain: solana",
            "token_symbol: PYUSD",
            "token_symbol: USDT",
            "family: evm",
            "family: svm",
        ]:
            self.assertIn(expected, chains)

    def test_labels_seed_status_documents_d3_gate(self) -> None:
        labels = (ROOT / "config" / "labels_seed.yaml").read_text(encoding="utf-8")
        self.assertIn("status: pending_human_seed", labels)
        self.assertIn("public_launch_blocked: true", labels)
        self.assertIn("sample_benchmark_demo_allowed: true", labels)

    def test_fee_schedule_is_empty_manual_config(self) -> None:
        fees = (ROOT / "config" / "fee_schedule.yaml").read_text(encoding="utf-8")
        self.assertIn("external_api_calls_allowed: false", fees)
        self.assertIn("schedules: []", fees)


if __name__ == "__main__":
    unittest.main()
