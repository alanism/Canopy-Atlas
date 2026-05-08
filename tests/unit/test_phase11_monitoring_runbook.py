import pathlib
import unittest

from pipeline.monitoring import (
    ALERT_GROUPS,
    ALERT_INVENTORY,
    OUTCOME_METRICS,
    OutcomeInstrumentation,
    emit_alert,
    evaluate_upstream_health_alerts,
    group_alerts,
    validate_required_gate_fields,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "runbook.md"
ALERT_DOC = ROOT / "docs" / "monitoring-alerts.md"
API_SERVER = ROOT / "api" / "server.py"


class TestPhase11MonitoringRunbook(unittest.TestCase):
    def test_required_alert_inventory_exists(self) -> None:
        for alert_type in (
            "correction_inbox_sla_breach",
            "missing_validation_gate_fields",
            "stale_running_lock",
            "upstream_health_non_ok",
            "upstream_freshness_exceeded",
        ):
            self.assertIn(alert_type, ALERT_INVENTORY)
            self.assertIn("severity", ALERT_INVENTORY[alert_type])

    def test_alert_grouping_collapses_root_causes(self) -> None:
        grouped = group_alerts(["cache_unavailable", "api_503", "upstream_health_non_ok"])
        self.assertEqual(grouped["redis_outage"], ["cache_unavailable", "api_503"])
        self.assertEqual(grouped["upstream_stale"], ["upstream_health_non_ok"])
        self.assertIn("health_api_degraded", ALERT_GROUPS["upstream_stale"])

    def test_upstream_health_alerts_cover_non_ok_and_freshness(self) -> None:
        alerts = evaluate_upstream_health_alerts(
            {"status": "degraded", "gates": {"freshness": {"max_freshness_hours": 9}}}
        )
        self.assertEqual([alert.alert_type for alert in alerts], [
            "upstream_health_non_ok",
            "upstream_freshness_exceeded",
        ])

    def test_missing_validation_gate_fields_alerts(self) -> None:
        alerts = validate_required_gate_fields({"gates": {"freshness": {}, "run_status": {}}})
        self.assertEqual(alerts[0].alert_type, "missing_validation_gate_fields")
        self.assertEqual(alerts[0].payload["missing"], ["reconciliation"])

    def test_product_outcome_metrics_are_captured(self) -> None:
        outcomes = OutcomeInstrumentation()
        outcomes.record_v0_request(path="/v0/dashboard-summary", ip_address="1.1.1.1")
        outcomes.record_v0_request(path="/v0/dashboard-summary", ip_address="1.1.1.1")
        outcomes.record_v0_request(path="/v0/methodology", ip_address="2.2.2.2")
        outcomes.record_event("api_access_cta_clicks")
        snapshot = outcomes.snapshot()
        self.assertEqual(snapshot["unique_v0_ips"], 2)
        self.assertEqual(snapshot["dashboard_summary_requests"], 2)
        self.assertEqual(snapshot["methodology_page_views"], 1)
        self.assertEqual(snapshot["api_access_cta_clicks"], 1)
        self.assertEqual(set(snapshot), set(OUTCOME_METRICS))

    def test_emit_alert_is_structured(self) -> None:
        alert = emit_alert("cache_unavailable", payload={"endpoint": "/v0/status"})
        self.assertEqual(alert.severity, "critical")
        self.assertEqual(alert.root_cause, "redis_outage")
        self.assertEqual(alert.payload["endpoint"], "/v0/status")

    def test_runbook_has_required_sections_and_real_commands(self) -> None:
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for heading in (
            "Startup",
            "Daily Monitoring",
            "Alert Response",
            "Known Failure Modes",
            "Stale-Run Handling",
            "Cache Rollback",
            "Upstream Evidence Contract Drift",
            "Upstream Evidence Health API Recovery",
            "Label Correction Workflow",
            "Security Incident Response",
            "Shutdown And Restore",
        ):
            self.assertIn(f"## {heading}", runbook)
        self.assertIn("gcloud run services list", runbook)
        self.assertIn("curl -H", runbook)

    def test_alert_docs_include_grouping_and_outcomes(self) -> None:
        doc = ALERT_DOC.read_text(encoding="utf-8")
        self.assertIn("Upstream Evidence Stale", doc)
        self.assertIn("upstream_health_non_ok", doc)
        self.assertIn("dashboard_summary_requests", doc)
        self.assertIn("/internal/outcome-metrics", doc)

    def test_api_server_exposes_outcome_metrics_endpoint(self) -> None:
        source = API_SERVER.read_text(encoding="utf-8")
        self.assertIn("OutcomeInstrumentation", source)
        self.assertIn("/internal/outcome-metrics", source)
        self.assertIn("record_v0_request", source)


if __name__ == "__main__":
    unittest.main()
