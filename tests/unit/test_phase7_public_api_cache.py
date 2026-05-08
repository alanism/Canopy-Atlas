import json
import pathlib
import threading
import unittest

from api.cache import MemorySnapshotStore, cache_key, promote_cache_payload
from api.payloads import build_dashboard_summary_payload, build_investor_preview_dashboard_payload
from api.public_api import dashboard_summary, status


ROOT = pathlib.Path(__file__).resolve().parents[2]


class MemoryCache:
    def __init__(self) -> None:
        self.values = {}
        self.get_count = 0

    def get(self, key: str):
        self.get_count += 1
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class FailingCache(MemoryCache):
    def get(self, key: str):
        raise RuntimeError("cache unavailable")


def dashboard_payload(**meta_overrides):
    meta = {
        "cache_generation_timestamp": "2026-05-06T00:05:00Z",
        "metrics_timestamp": "2026-05-06T00:05:00Z",
        "data_window_start": "2026-05-06T00:00:00Z",
        "data_window_end": "2026-05-06T01:00:00Z",
        "last_validated_at": "2026-05-06T00:00:00Z",
        "data_quality_status": "partially_validated",
        "labeled_volume_pct": 0.0,
        "long_tail_volume_pct": 1.0,
        "x402_signal_status": "unavailable",
        "x402_signal_detected": False,
    }
    meta.update(meta_overrides)
    return build_dashboard_summary_payload(
        meta=meta,
        leaderboard=[{"route_id": "solana_PYUSD_unknown_long_tail"}],
        route_share=[{"route_id": "solana_PYUSD_unknown_long_tail", "route_share_pct": 1.0}],
        settlement_health=[{"route_id": "solana_PYUSD_unknown_long_tail", "observed_settlement_rate": 1.0}],
    )


class TestPhase7PublicApiCache(unittest.TestCase):
    def test_cache_hit_bigquery_not_called(self) -> None:
        cache = MemoryCache()
        promote_cache_payload(
            cache=cache,
            snapshot_store=None,
            key=cache_key("dashboard-summary", "1h"),
            payload=dashboard_payload(),
        )
        status_code, payload = dashboard_summary(cache=cache, window="1h")
        self.assertEqual(status_code, 200)
        self.assertFalse(payload["meta"]["suitable_for_runtime_routing"])
        self.assertEqual(cache.get_count, 1)

    def test_cache_miss_returns_503_in_production(self) -> None:
        status_code, payload = dashboard_summary(cache=MemoryCache(), window="1h")
        self.assertEqual(status_code, 503)
        self.assertEqual(payload["error"], "cache_temporarily_unavailable")

    def test_redis_failure_returns_503(self) -> None:
        status_code, payload = dashboard_summary(cache=FailingCache(), window="1h")
        self.assertEqual(status_code, 503)
        self.assertEqual(payload["message"], "Cache temporarily unavailable. Retry in 30 seconds.")

    def test_redis_failure_returns_snapshot_when_available(self) -> None:
        snapshot_store = MemorySnapshotStore()
        snapshot_store.set_snapshot(cache_key("dashboard-summary", "1h"), dashboard_payload())
        status_code, payload = dashboard_summary(cache=FailingCache(), snapshot_store=snapshot_store, window="1h")
        self.assertEqual(status_code, 200)
        self.assertEqual(payload["meta"]["runtime_warning"], "serving_last_known_good")

    def test_public_api_does_not_import_bq_client(self) -> None:
        for path in (ROOT / "api").glob("*.py"):
            content = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("bigquery", content)
            self.assertNotIn("bq_client", content)

    def test_concurrent_public_requests_do_not_trigger_bq(self) -> None:
        cache = MemoryCache()
        promote_cache_payload(
            cache=cache,
            snapshot_store=None,
            key=cache_key("dashboard-summary", "1h"),
            payload=dashboard_payload(),
        )
        results = []

        def request_once():
            results.append(dashboard_summary(cache=cache, window="1h")[0])

        threads = [threading.Thread(target=request_once) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, [200, 200, 200, 200, 200])

    def test_dashboard_summary_returns_all_panels(self) -> None:
        cache = MemoryCache()
        promote_cache_payload(
            cache=cache,
            snapshot_store=None,
            key=cache_key("dashboard-summary", "1h"),
            payload=dashboard_payload(),
        )
        _, payload = dashboard_summary(cache=cache, window="1h")
        panels = payload["data"]["panels"]
        self.assertIn("observed_effective_cost_leaderboard", panels)
        self.assertIn("volume_weighted_route_share", panels)
        self.assertIn("observed_settlement_health_x_cost", panels)

    def test_status_exposes_x402_signal_status(self) -> None:
        cache = MemoryCache()
        promote_cache_payload(
            cache=cache,
            snapshot_store=None,
            key=cache_key("status"),
            payload={"meta": {"x402_signal_status": "unavailable"}, "data": {"ok": True}},
        )
        status_code, payload = status(cache)
        self.assertEqual(status_code, 200)
        self.assertEqual(payload["meta"]["x402_signal_status"], "unavailable")
        self.assertEqual(payload["meta"]["dashboard_title"], "Observed Stablecoin Route Benchmark")

    def test_refresh_param_blocked(self) -> None:
        status_code, payload = dashboard_summary(cache=MemoryCache(), window="1h", query_params={"refresh": "1"})
        self.assertEqual(status_code, 400)
        self.assertIn("refresh", payload["message"])

    def test_invalid_window_returns_400(self) -> None:
        status_code, payload = dashboard_summary(cache=MemoryCache(), window="2h")
        self.assertEqual(status_code, 400)
        self.assertEqual(payload["message"], "invalid window")

    def test_cache_payload_is_json_serializable(self) -> None:
        encoded = json.dumps(dashboard_payload())
        self.assertIn("Observed Stablecoin Route Benchmark", encoded)

    def test_investor_preview_payload_has_visible_non_production_rows(self) -> None:
        payload = build_investor_preview_dashboard_payload()
        panels = payload["data"]["panels"]
        self.assertEqual(payload["meta"]["data_quality_status"], "preview_bootstrap")
        self.assertFalse(payload["meta"]["suitable_for_runtime_routing"])
        self.assertIn("illustrative and not production evidence", payload["meta"]["runtime_warning"])
        self.assertGreater(len(panels["observed_effective_cost_leaderboard"]), 0)
        self.assertGreater(len(panels["volume_weighted_route_share"]), 0)
        self.assertGreater(len(panels["observed_settlement_health_x_cost"]), 0)
        self.assertGreater(len(panels["under_review_routes"]), 0)


if __name__ == "__main__":
    unittest.main()
