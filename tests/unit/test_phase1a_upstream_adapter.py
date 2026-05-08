import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

from pipeline.adapter.phase1a_decision import decide_ingestion_mode, write_decision_artifacts
from pipeline.adapter.upstream_gates import (
    FRESHNESS_SQL,
    RECONCILIATION_SQL,
    SIGNAL_AVAILABILITY_SQL,
    TOKEN_ALLOWLIST_SQL,
)
from pipeline.adapter.upstream_health_client import (
    UpstreamHealthError,
    ServiceHealth,
    parse_service_health,
)
from pipeline.adapter.upstream_schema_inspector import TRANSFER_CONTRACT_COLUMNS_SQL, TRANSFER_SAMPLE_SQL


def healthy_payload(status: str = "ok") -> dict[str, Any]:
    return {
        "contract_version": "atlas-upstream-health-v1",
        "status": status,
        "suitable_for_runtime_routing": False,
        "gates": {
            "freshness": {"passed": status == "ok"},
            "reconciliation": {"passed": True},
            "run_status": {"passed": True},
        },
        "x402": {
            "signal_source_available": False,
            "signal_fields_present": [],
            "rpc_pointer_available": True,
        },
    }


class FakeUpstreamQuery:
    def __init__(
        self,
        *,
        signal_available: bool = False,
        token_allowed: bool = True,
        missing_columns: Optional[set[str]] = None,
        freshness_hours: float = 2.0,
        match_rate: float = 0.998,
        reconciliation_passed: bool = True,
    ) -> None:
        self.calls: list[str] = []
        self.signal_available = signal_available
        self.token_allowed = token_allowed
        self.missing_columns = missing_columns or set()
        self.freshness_hours = freshness_hours
        self.match_rate = match_rate
        self.reconciliation_passed = reconciliation_passed

    def __call__(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(sql)
        if sql == TOKEN_ALLOWLIST_SQL:
            return [{"chain": "solana", "token_symbol": "PYUSD", "is_active": True}] if self.token_allowed else []
        if sql == SIGNAL_AVAILABILITY_SQL:
            return [
                {
                    "x402_signal_source_available": self.signal_available,
                    "rpc_pointer_available": True,
                    "memo_field_available": self.signal_available,
                    "program_id_available": self.signal_available,
                    "raw_instruction_ref_available": self.signal_available,
                    "notes": "mock",
                }
            ]
        if sql == FRESHNESS_SQL:
            return [
                {
                    "token_symbol": "PYUSD",
                    "chain": "solana",
                    "freshness_hours": self.freshness_hours,
                    "global_max_freshness_hours": self.freshness_hours,
                }
            ]
        if sql == RECONCILIATION_SQL:
            return [
                {
                    "token_symbol": "PYUSD",
                    "chain": "solana",
                    "run_timestamp": "2026-05-06T08:10:00Z",
                    "match_rate": self.match_rate,
                    "gate_passed": self.reconciliation_passed,
                }
            ]
        if sql == TRANSFER_CONTRACT_COLUMNS_SQL:
            columns = {
                "chain",
                "block_timestamp",
                "transaction_hash",
                "log_index",
                "signature",
                "instruction_index",
                "is_inner",
                "inner_instruction_index",
                "from_address",
                "to_address",
                "token_address",
                "token_symbol",
                "amount_raw",
                "decimals",
                "amount_tokens",
                "block_date",
            } - self.missing_columns
            return [{"column_name": column} for column in columns]
        if sql == TRANSFER_SAMPLE_SQL:
            return [
                {
                    "chain": "solana",
                    "token_symbol": "PYUSD",
                    "signature": "sig",
                    "instruction_index": 0,
                    "is_inner": False,
                    "inner_instruction_index": None,
                }
            ]
        raise AssertionError(f"unexpected SQL: {sql}")


class TestPhase1AUpstream(unittest.TestCase):
    def test_health_client_requires_expected_contract(self) -> None:
        payload = healthy_payload()
        payload["contract_version"] = "other"
        with self.assertRaises(UpstreamHealthError):
            parse_service_health(payload)

    def test_health_client_rejects_runtime_routing_true(self) -> None:
        payload = healthy_payload()
        payload["suitable_for_runtime_routing"] = True
        with self.assertRaises(UpstreamHealthError):
            parse_service_health(payload)

    def test_phase1a_outputs_ingestion_mode(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery())
        self.assertEqual(decision.ingestion_mode, "adapter")
        self.assertTrue(decision.upstream_contract_passed)
        self.assertFalse(decision.x402_signal_source_available)

    def test_phase1a_uses_versioned_upstream_contract_views(self) -> None:
        health = parse_service_health(healthy_payload())
        fake_query = FakeUpstreamQuery()
        decide_ingestion_mode(health, fake_query)
        joined_calls = "\n".join(fake_query.calls)
        self.assertIn("token_symbol_contract_v1", joined_calls)
        self.assertIn("x402_signal_availability_v1", joined_calls)
        self.assertIn("upstream_freshness_summary_v1", joined_calls)
        self.assertIn("upstream_reconciliation_latest_v1", joined_calls)
        self.assertIn("upstream_evidence_contract_v1", joined_calls)

    def test_upstream_schema_contract(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(missing_columns={"signature"}))
        self.assertEqual(decision.ingestion_mode, "pivot")
        self.assertIn("signature", decision.missing_fields)

    def test_upstream_table_token_symbol_matches_config(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(token_allowed=False))
        self.assertEqual(decision.ingestion_mode, "pivot")
        self.assertFalse(decision.token_symbol_check_passed)

    def test_x402_signal_source_detection(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(signal_available=True))
        self.assertEqual(decision.ingestion_mode, "adapter_plus_signal_fetch")
        self.assertTrue(decision.x402_signal_source_available)

    def test_degraded_health_blocks_validated_status_but_not_contract_detection(self) -> None:
        health = parse_service_health(healthy_payload(status="degraded"))
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(freshness_hours=176.0))
        self.assertEqual(decision.ingestion_mode, "adapter")
        self.assertTrue(decision.upstream_contract_passed)
        self.assertEqual(decision.upstream_validation_status, "stale")
        self.assertIn("degraded", decision.decision_notes)

    def test_missing_upstream_identity_fields_triggers_pivot(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(missing_columns={"instruction_index"}))
        self.assertEqual(decision.ingestion_mode, "pivot")
        self.assertIn("instruction_index", decision.missing_fields)

    def test_valid_transfer_but_missing_x402_signal_sets_unknown(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery(signal_available=False))
        self.assertEqual(decision.ingestion_mode, "adapter")
        self.assertFalse(decision.x402_signal_source_available)
        self.assertIn("benchmark fallback", decision.decision_notes)

    def test_phase1a_writes_artifacts(self) -> None:
        health = parse_service_health(healthy_payload())
        decision = decide_ingestion_mode(health, FakeUpstreamQuery())
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config" / "ingestion_mode.json"
            doc_path = Path(tmp_dir) / "docs" / "upstream-evidence-contract.md"
            write_decision_artifacts(decision, health, config_path=config_path, doc_path=doc_path)
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["ingestion_mode"], "adapter")
            self.assertIn("atlas-upstream-health-v1", doc_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
