import unittest

from pipeline.validate.validation import (
    build_row_sample_validation_log,
    compute_row_sample_validation,
    derive_data_quality_status,
)


class TestPhase5Validation(unittest.TestCase):
    def test_upstream_failed_reconciliation_blocks_validated_status(self) -> None:
        status = derive_data_quality_status(
            upstream_match_rate=0.98,
            upstream_validation_status="partial",
            row_sample_match_rate=1.0,
            freshness_within_threshold=True,
            under_review=False,
        )
        self.assertEqual(status, "partially_validated")

    def test_upstream_stale_reconciliation_sets_partial_or_stale(self) -> None:
        status = derive_data_quality_status(
            upstream_match_rate=1.0,
            upstream_validation_status="stale",
            row_sample_match_rate=1.0,
            freshness_within_threshold=False,
            under_review=False,
        )
        self.assertEqual(status, "stale")

    def test_low_volume_validation_uses_actual_sample_size(self) -> None:
        result = compute_row_sample_validation(tx_count=5, configured_sample_size=20, matched_count=4)
        self.assertEqual(result.actual_sample_size, 5)
        self.assertEqual(result.row_sample_match_rate, 0.8)
        self.assertFalse(result.gate_passed)

    def test_five_of_five_matches_yields_1_0(self) -> None:
        result = compute_row_sample_validation(tx_count=5, configured_sample_size=20, matched_count=5)
        self.assertEqual(result.actual_sample_size, 5)
        self.assertEqual(result.row_sample_match_rate, 1.0)
        self.assertTrue(result.gate_passed)

    def test_row_sample_mismatch_blocks_validated(self) -> None:
        status = derive_data_quality_status(
            upstream_match_rate=1.0,
            upstream_validation_status="validated",
            row_sample_match_rate=0.98,
            freshness_within_threshold=True,
            under_review=False,
        )
        self.assertEqual(status, "partially_validated")

    def test_own_node_mock_never_validated(self) -> None:
        record = build_row_sample_validation_log(
            run_id="run-1",
            run_timestamp="2026-05-06T00:00:00Z",
            chain="solana",
            stablecoin="PYUSD",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T01:00:00Z",
            tx_count=5,
            configured_sample_size=20,
            matched_count=5,
            upstream_match_rate=1.0,
            upstream_last_validated_at="2026-04-29T02:18:53Z",
            upstream_validation_status="validated",
            source_b="own_node",
        )
        self.assertFalse(record.gate_passed)
        self.assertEqual(record.validation_status, "partial")
        self.assertEqual(record.row_sample_match_rate, 1.0)

    def test_validation_log_includes_upstream_provenance(self) -> None:
        record = build_row_sample_validation_log(
            run_id="run-1",
            run_timestamp="2026-05-06T00:00:00Z",
            chain="solana",
            stablecoin="PYUSD",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T01:00:00Z",
            tx_count=5,
            configured_sample_size=20,
            matched_count=5,
            upstream_match_rate=1.0,
            upstream_last_validated_at="2026-04-29T02:18:53Z",
            upstream_validation_status="stale",
        )
        self.assertEqual(record.upstream_match_rate, 1.0)
        self.assertEqual(record.upstream_last_validated_at, "2026-04-29T02:18:53Z")
        self.assertEqual(record.upstream_validation_status, "stale")
        self.assertEqual(record.sample_size, 5)

    def test_validated_requires_upstream_and_x402_match_rates(self) -> None:
        status = derive_data_quality_status(
            upstream_match_rate=1.0,
            upstream_validation_status="validated",
            row_sample_match_rate=1.0,
            freshness_within_threshold=True,
            under_review=False,
        )
        self.assertEqual(status, "validated")


if __name__ == "__main__":
    unittest.main()
