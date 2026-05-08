from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from api.agent_proxy import PAID_EVENT_TYPE, metrics_cache_filename
from scripts.aggregate_agentcash_metrics import aggregate_events, write_summaries


NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


class TestPhase15AgentCashMetrics(unittest.TestCase):
    def test_aggregate_counts_paid_revenue_wallets_and_dedupes_events(self) -> None:
        events = [
            _event("evt-1", "paid_success", wallet_id="wallet_a", network="solana", charge="0.05", latency=10),
            _event("evt-1", "paid_success", wallet_id="wallet_a", network="solana", charge="0.05", latency=10),
            _event("evt-2", "paid_success", wallet_id="wallet_b", network="base", charge="0.05", latency=20),
            _event("evt-3", "payment_required", latency=5),
            _event("evt-4", "payment_rejected", latency=7),
            _event("evt-5", "rate_limited", wallet_id="wallet_a", latency=11),
            _event("evt-6", "benchmark_unavailable", wallet_id="wallet_a", latency=13),
            {"event_type": "unrelated", "event_id": "evt-7"},
        ]

        payload = aggregate_events(events, now=NOW)["24h"]
        totals = payload["data"]["totals"]

        self.assertEqual(totals["paid_success_count"], 2)
        self.assertEqual(totals["gross_usdc"], "0.10")
        self.assertEqual(totals["payment_required_count"], 1)
        self.assertEqual(totals["payment_rejected_count"], 1)
        self.assertEqual(totals["rate_limited_count"], 1)
        self.assertEqual(totals["benchmark_unavailable_count"], 1)
        self.assertEqual(totals["unique_payer_wallets"], 2)
        self.assertEqual(payload["data"]["breakdowns"]["top_wallets"][0]["wallet_id"], "wallet_a")

    def test_aggregate_writes_cache_files_for_all_windows(self) -> None:
        summaries = aggregate_events([_event("evt-1", "paid_success", wallet_id="wallet_a")], now=NOW)
        with tempfile.TemporaryDirectory() as tmpdir:
            write_summaries(summaries, Path(tmpdir))
            for window in ("1h", "24h", "7d"):
                path = Path(tmpdir, metrics_cache_filename(window))
                self.assertTrue(path.exists())
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["meta"]["window"], window)

    def test_empty_window_returns_explicit_empty_state(self) -> None:
        payload = aggregate_events([], now=NOW)["24h"]
        self.assertEqual(payload["meta"]["data_quality_status"], "empty")
        self.assertEqual(payload["data"]["totals"]["paid_success_count"], 0)


def _event(
    event_id: str,
    outcome: str,
    *,
    wallet_id: str | None = None,
    network: str | None = None,
    charge: str = "0.05",
    latency: float = 1.0,
) -> dict[str, object]:
    return {
        "event_type": PAID_EVENT_TYPE,
        "event_id": event_id,
        "emitted_at": "2026-05-07T11:30:00+00:00",
        "outcome": outcome,
        "status_code": 200,
        "window": "1h",
        "limit": 3,
        "charge_usdc": charge,
        "payment_network": network,
        "latency_ms": latency,
        "wallet_id": wallet_id,
    }


if __name__ == "__main__":
    unittest.main()
