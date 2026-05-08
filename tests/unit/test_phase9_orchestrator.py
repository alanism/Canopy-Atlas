import pathlib
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from api.internal_api import internal_run
from pipeline.orchestrator import (
    MemoryAlertSink,
    MemoryPipelineRunStore,
    NamedStage,
    OrchestratorConfig,
    PipelineRun,
    run_orchestrator,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEDULER_CONFIG = ROOT / "config" / "cloud_scheduler_jobs.yaml"


class RecordingStage(NamedStage):
    def __init__(self, name: str, calls: list[str]) -> None:
        super().__init__(name)
        self.calls = calls

    def run(self, context):
        self.calls.append(self.name)
        return {"ok": True}


class TestPhase9Orchestrator(unittest.TestCase):
    def test_scheduler_target_matches_cloud_run_service_mode(self) -> None:
        config = SCHEDULER_CONFIG.read_text(encoding="utf-8")
        self.assertIn("x402-short-window", config)
        self.assertIn("x402-long-window", config)
        self.assertIn("/internal/run", config)
        self.assertIn("oidc_service_account_email", config)
        self.assertIn("oidc_audience", config)
        self.assertNotIn("run.googleapis.com/apis/run.googleapis.com", config)

    def test_private_internal_run_rejects_public_invocation(self) -> None:
        with patch.dict("os.environ", {"ATLAS_ORCHESTRATOR_TOKEN": "test-token"}, clear=False):
            status_code, payload = internal_run(
                method="POST",
                headers={},
                body={"cadence": "short", "run_id": "run-public"},
                store=MemoryPipelineRunStore(),
                alert_sink=MemoryAlertSink(),
            )
        self.assertEqual(status_code, 403)
        self.assertEqual(payload["error"], "forbidden")

    def test_private_internal_run_fails_closed_when_token_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            status_code, payload = internal_run(
                method="POST",
                headers={"Authorization": "Bearer anything"},
                body={"cadence": "short", "run_id": "run-disabled"},
                store=MemoryPipelineRunStore(),
                alert_sink=MemoryAlertSink(),
            )
        self.assertEqual(status_code, 503)
        self.assertEqual(payload["error"], "orchestrator_disabled")

    def test_recent_running_lock_skips(self) -> None:
        now = datetime(2026, 5, 6, 0, 5, tzinfo=timezone.utc)
        store = MemoryPipelineRunStore()
        store.insert_run(
            PipelineRun(
                run_id="active",
                started_at=now - timedelta(minutes=4),
                status="running",
                trigger_source="scheduler",
                chain="solana",
                stablecoin="PYUSD",
            )
        )
        result = run_orchestrator(
            payload={"cadence": "short", "run_id": "overlap"},
            store=store,
            alert_sink=MemoryAlertSink(),
            now=now,
        )
        self.assertEqual(result.status, "skipped_overlap")
        self.assertEqual(result.reason, "recent_running_lock")
        self.assertEqual(store.runs[-1].status, "skipped_overlap")

    def test_stale_running_lock_does_not_brick_forever(self) -> None:
        now = datetime(2026, 5, 6, 0, 20, tzinfo=timezone.utc)
        store = MemoryPipelineRunStore()
        alerts = MemoryAlertSink()
        store.insert_run(
            PipelineRun(
                run_id="stale-active",
                started_at=now - timedelta(minutes=60),
                status="running",
                trigger_source="scheduler",
                chain="solana",
                stablecoin="PYUSD",
            )
        )
        first = run_orchestrator(
            payload={"cadence": "short", "run_id": "stale-skip"},
            store=store,
            alert_sink=alerts,
            config=OrchestratorConfig(overlap_lock_minutes=10),
            now=now,
        )
        second = run_orchestrator(
            payload={"cadence": "short", "run_id": "next-run"},
            store=store,
            alert_sink=alerts,
            now=now + timedelta(minutes=5),
        )
        self.assertEqual(first.status, "skipped_overlap")
        self.assertEqual(store.runs[0].status, "stale")
        self.assertEqual(store.runs[0].last_error, "failed_stale_lock")
        self.assertEqual(second.status, "success")

    def test_stale_lock_requires_alert(self) -> None:
        now = datetime(2026, 5, 6, 0, 20, tzinfo=timezone.utc)
        store = MemoryPipelineRunStore()
        alerts = MemoryAlertSink()
        store.insert_run(
            PipelineRun(
                run_id="stale-active",
                started_at=now - timedelta(minutes=30),
                status="running",
                trigger_source="scheduler",
                chain="solana",
                stablecoin="PYUSD",
            )
        )
        run_orchestrator(
            payload={"cadence": "short", "run_id": "stale-skip"},
            store=store,
            alert_sink=alerts,
            now=now,
        )
        self.assertEqual(alerts.alerts[0]["alert_type"], "stale_running_lock")
        self.assertEqual(alerts.alerts[0]["payload"]["stale_run_id"], "stale-active")

    def test_pipeline_status_uses_update_not_merge(self) -> None:
        store = MemoryPipelineRunStore()
        result = run_orchestrator(
            payload={"cadence": "short", "run_id": "run-update"},
            store=store,
            alert_sink=MemoryAlertSink(),
            now=datetime(2026, 5, 6, 0, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(store.update_calls[-1]["operation"], "UPDATE")

    def test_5min_cadence_runs_15m_1h_only(self) -> None:
        result = run_orchestrator(
            payload={"cadence": "short", "run_id": "short-run"},
            store=MemoryPipelineRunStore(),
            alert_sink=MemoryAlertSink(),
            now=datetime(2026, 5, 6, 0, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(result.windows, ("15m", "1h"))
        self.assertIn("metrics:15m", result.phases_run)
        self.assertIn("metrics:1h", result.phases_run)
        self.assertNotIn("metrics:24h", result.phases_run)
        self.assertNotIn("metrics:7d", result.phases_run)

    def test_hourly_cadence_runs_24h_7d(self) -> None:
        result = run_orchestrator(
            payload={"cadence": "long", "run_id": "long-run"},
            store=MemoryPipelineRunStore(),
            alert_sink=MemoryAlertSink(),
            now=datetime(2026, 5, 6, 1, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result.windows, ("24h", "7d"))
        self.assertIn("metrics:24h", result.phases_run)
        self.assertIn("metrics:7d", result.phases_run)
        self.assertNotIn("metrics:15m", result.phases_run)
        self.assertNotIn("metrics:1h", result.phases_run)

    def test_full_dag_runs_in_order(self) -> None:
        calls: list[str] = []
        stages = [
            RecordingStage("ingest", calls),
            RecordingStage("normalize", calls),
            RecordingStage("validate", calls),
            RecordingStage("metrics:15m", calls),
            RecordingStage("metrics:1h", calls),
            RecordingStage("validate_cache_payload", calls),
            RecordingStage("promote_cache", calls),
        ]
        result = run_orchestrator(
            payload={"cadence": "short", "run_id": "ordered-run"},
            store=MemoryPipelineRunStore(),
            alert_sink=MemoryAlertSink(),
            stages=stages,
            now=datetime(2026, 5, 6, 0, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(calls, [stage.name for stage in stages])


if __name__ == "__main__":
    unittest.main()
