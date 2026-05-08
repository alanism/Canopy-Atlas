import pathlib
import unittest

from pipeline.metrics.rolling_metrics import (
    ValidationProvenance,
    build_route_metric,
    compute_metric_id,
    validation_quality_status,
    windows_for_cadence,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
METRICS_SQL = ROOT / "sql" / "metrics" / "rolling_route_metrics.sql"


class TestPhase6RollingMetrics(unittest.TestCase):
    def test_metrics_join_validation_log(self) -> None:
        metric = build_route_metric(
            rows=[{"amount_usd": 10.0, "total_observed_fee_usd": 0.1}],
            validation=ValidationProvenance(
                source_count=3,
                row_sample_match_rate=1.0,
                last_validated_at="2026-05-06T00:00:00Z",
                validation_type="row_sample",
                data_quality_status="validated",
            ),
            cache_generation_timestamp="2026-05-06T00:05:00Z",
            metrics_timestamp="2026-05-06T00:05:00Z",
            window_label="15m",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T00:15:00Z",
            chain="solana",
            stablecoin="PYUSD",
            route_id="solana_PYUSD_unknown_long_tail",
            total_observed_volume_usd=10.0,
        )
        self.assertEqual(metric.source_count, 3)
        self.assertEqual(metric.row_sample_match_rate, 1.0)
        self.assertEqual(metric.data_quality_status, "validated")

    def test_missing_validation_becomes_partially_validated(self) -> None:
        metric = build_route_metric(
            rows=[{"amount_usd": 10.0, "total_observed_fee_usd": 0.1}],
            validation=None,
            cache_generation_timestamp="2026-05-06T00:05:00Z",
            metrics_timestamp="2026-05-06T00:05:00Z",
            window_label="15m",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T00:15:00Z",
            chain="solana",
            stablecoin="PYUSD",
            route_id="solana_PYUSD_unknown_long_tail",
            total_observed_volume_usd=10.0,
        )
        self.assertEqual(metric.source_count, 0)
        self.assertEqual(metric.data_quality_status, "partially_validated")

    def test_stale_validation_sets_stale_status(self) -> None:
        self.assertEqual(
            validation_quality_status(source_count=3, row_sample_match_rate=1.0, validation_stale=True),
            "stale",
        )

    def test_match_rate_below_threshold_blocks_validated_status(self) -> None:
        self.assertEqual(
            validation_quality_status(source_count=3, row_sample_match_rate=0.98, validation_stale=False),
            "partially_validated",
        )

    def test_same_run_timestamp_produces_same_metric_ids(self) -> None:
        kwargs = {
            "chain": "solana",
            "stablecoin": "PYUSD",
            "route_id": "solana_PYUSD_unknown_long_tail",
            "window_label": "15m",
            "window_start": "2026-05-06T00:00:00Z",
        }
        self.assertEqual(compute_metric_id(**kwargs), compute_metric_id(**kwargs))

    def test_metrics_rerun_idempotent(self) -> None:
        kwargs = {
            "rows": [{"amount_usd": 10.0, "total_observed_fee_usd": 0.1}],
            "validation": None,
            "cache_generation_timestamp": "2026-05-06T00:05:00Z",
            "metrics_timestamp": "2026-05-06T00:05:00Z",
            "window_label": "15m",
            "window_start": "2026-05-06T00:00:00Z",
            "window_end": "2026-05-06T00:15:00Z",
            "chain": "solana",
            "stablecoin": "PYUSD",
            "route_id": "solana_PYUSD_unknown_long_tail",
            "total_observed_volume_usd": 10.0,
        }
        self.assertEqual(build_route_metric(**kwargs).metric_id, build_route_metric(**kwargs).metric_id)

    def test_no_generate_uuid_in_sql(self) -> None:
        self.assertNotIn("GENERATE_UUID", METRICS_SQL.read_text(encoding="utf-8").upper())

    def test_no_current_timestamp_for_logical_windows(self) -> None:
        self.assertNotIn("CURRENT_TIMESTAMP", METRICS_SQL.read_text(encoding="utf-8").upper())

    def test_metrics_sql_has_block_date_filter(self) -> None:
        sql = METRICS_SQL.read_text(encoding="utf-8")
        self.assertIn("block_date BETWEEN @window_start_date AND @window_end_date", sql)
        self.assertIn("@run_timestamp", sql)
        self.assertIn("x402_validation_log", sql)

    def test_null_amount_excluded_from_volume_weighting(self) -> None:
        metric = build_route_metric(
            rows=[
                {"amount_usd": 10.0, "total_observed_fee_usd": 1.0},
                {"amount_usd": None, "total_observed_fee_usd": 99.0},
            ],
            validation=None,
            cache_generation_timestamp="2026-05-06T00:05:00Z",
            metrics_timestamp="2026-05-06T00:05:00Z",
            window_label="15m",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T00:15:00Z",
            chain="solana",
            stablecoin="PYUSD",
            route_id="solana_PYUSD_unknown_long_tail",
            total_observed_volume_usd=10.0,
        )
        self.assertEqual(metric.route_volume_usd, 10.0)
        self.assertEqual(metric.observed_cost_pct, 0.1)

    def test_null_amount_increments_quality_issue_count(self) -> None:
        metric = build_route_metric(
            rows=[
                {"amount_usd": 10.0, "total_observed_fee_usd": 1.0},
                {"amount_usd": None, "total_observed_fee_usd": 99.0},
            ],
            validation=ValidationProvenance(3, 1.0, "2026-05-06T00:00:00Z", "row_sample", "validated"),
            cache_generation_timestamp="2026-05-06T00:05:00Z",
            metrics_timestamp="2026-05-06T00:05:00Z",
            window_label="15m",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T00:15:00Z",
            chain="solana",
            stablecoin="PYUSD",
            route_id="solana_PYUSD_unknown_long_tail",
            total_observed_volume_usd=10.0,
        )
        self.assertEqual(metric.data_quality_issue_count, 1)
        self.assertEqual(metric.data_quality_status, "partially_validated")

    def test_cadence_window_split(self) -> None:
        self.assertEqual(windows_for_cadence("short"), ("15m", "1h"))
        self.assertEqual(windows_for_cadence("long"), ("24h", "7d"))


if __name__ == "__main__":
    unittest.main()
