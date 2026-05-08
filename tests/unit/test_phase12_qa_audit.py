import pathlib
import unittest

from api.cache import MemorySnapshotStore, cache_key
from api.public_api import dashboard_summary
from pipeline.adapter.upstream_health_client import UpstreamHealthError, get_service_health
from pipeline.qa import audit_normalized_transaction, integration_readiness, observed_cost_pct


ROOT = pathlib.Path(__file__).resolve().parents[2]
QA_REPORT = ROOT / "docs" / "phase-12-qa-audit-report.md"
READINESS = ROOT / "docs" / "phase-12-integration-readiness-review.md"


class FailingCache:
    def get(self, key):
        raise RuntimeError("cache unavailable")


class EmptyCache:
    def get(self, key):
        return None


class TestPhase12QaAudit(unittest.TestCase):
    def test_audit_normalized_transaction_requires_core_fields(self) -> None:
        result = audit_normalized_transaction({"chain": "solana", "amount_usd": 1.0})
        self.assertFalse(result.passed)
        self.assertIn("route_id", result.missing_fields)
        self.assertIn("total_observed_fee_usd", result.missing_fields)

    def test_audit_normalized_transaction_blocks_self_transfers(self) -> None:
        row = {
            "amount_usd": 10.0,
            "amount_tokens": 10.0,
            "block_number": 123,
            "block_timestamp": "2026-05-06T00:00:00Z",
            "chain": "solana",
            "from_address": "a",
            "route_id": "route",
            "self_transfer_flag": True,
            "to_address": "a",
            "token_symbol": "PYUSD",
            "total_observed_fee_usd": 0.1,
        }
        result = audit_normalized_transaction(row)
        self.assertFalse(result.passed)
        self.assertIn("self-transfer", result.notes)

    def test_metric_spot_check_formula(self) -> None:
        self.assertEqual(
            observed_cost_pct(
                [
                    {"amount_usd": 100.0, "total_observed_fee_usd": 1.0},
                    {"amount_usd": 300.0, "total_observed_fee_usd": 3.0},
                ]
            ),
            0.01,
        )

    def test_cache_failure_behavior_passes_without_bigquery_fallback(self) -> None:
        status_code, payload = dashboard_summary(cache=FailingCache(), window="1h")
        self.assertEqual(status_code, 503)
        self.assertEqual(payload["error"], "cache_temporarily_unavailable")

    def test_cache_failure_serves_last_known_good_snapshot(self) -> None:
        snapshot = MemorySnapshotStore()
        snapshot.set_snapshot(
            cache_key("dashboard-summary", "1h"),
            {
                "meta": {"x402_signal_status": "unavailable"},
                "data": {"panels": {}},
            },
        )
        status_code, payload = dashboard_summary(cache=FailingCache(), snapshot_store=snapshot, window="1h")
        self.assertEqual(status_code, 200)
        self.assertEqual(payload["meta"]["runtime_warning"], "serving_last_known_good")

    def test_upstream_health_down_fails_closed(self) -> None:
        def fake_get(url, headers):
            return 503, b'{"contract_version":"atlas-upstream-health-v1","status":"unavailable","suitable_for_runtime_routing":false,"gates":{"freshness":{"passed":false},"reconciliation":{"passed":false},"run_status":{"passed":false}}}'

        with self.assertRaises(UpstreamHealthError):
            get_service_health(base_url="https://upstream.example", http_get=fake_get)

    def test_integration_readiness_classification(self) -> None:
        result = integration_readiness(
            upstream_status="stale",
            public_api_status="sample_bootstrap",
            product_claims_safe=True,
            cache_failure_verified=True,
            health_down_verified=True,
        )
        self.assertEqual(result["upstream"], "Yellow")
        self.assertEqual(result["public_api"], "sample mode")
        self.assertEqual(result["product_claims"], "safe")

    def test_qa_report_records_live_blockers_and_copy_status(self) -> None:
        report = QA_REPORT.read_text(encoding="utf-8")
        self.assertIn("public_sample_mode_ready", report)
        self.assertIn("YOUR_PROJECT_ID.YOUR_DATASET", report)
        self.assertIn("Observed Stablecoin Route Benchmark", report)
        self.assertIn("suitable_for_runtime_routing", report)
        self.assertIn("sample_mode_ready_external_data_optional", report)

    def test_integration_readiness_review_answers_required_surfaces(self) -> None:
        review = READINESS.read_text(encoding="utf-8")
        self.assertIn("Upstream evidence", review)
        self.assertIn("Decision Layer", review)
        self.assertIn("Public API", review)
        self.assertIn("Product Claims", review)
        self.assertIn("sample mode only", review)


if __name__ == "__main__":
    unittest.main()
