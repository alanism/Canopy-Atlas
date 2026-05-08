import pathlib
import unittest

from api.public_api import methodology


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_CONTRACT = ROOT / "deploy" / "cloud_run_services.yaml"
INTEGRATION_GUIDE = ROOT / "docs" / "integration-guide.md"
DATA_GUIDE = ROOT / "docs" / "data-and-decision-layer-integration.md"


class TestPhase10DeployPreview(unittest.TestCase):
    def test_deploy_contract_uses_placeholders_and_separate_services(self) -> None:
        contract = DEPLOY_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("project_id: YOUR_PROJECT_ID", contract)
        self.assertIn("canopy-atlas-api", contract)
        self.assertIn("canopy-atlas-dashboard", contract)
        self.assertIn("canopy-agent-proxy", contract)
        self.assertIn("API service account must hold no BigQuery write roles", contract)

    def test_orchestrator_contract_documents_token_requirement(self) -> None:
        contract = DEPLOY_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("/internal/run", contract)
        self.assertIn("ATLAS_ORCHESTRATOR_TOKEN", contract)
        self.assertIn("YOUR_DATASET", contract)
        self.assertNotIn("run.googleapis.com/apis/run.googleapis.com", contract)

    def test_public_methodology_endpoint_is_benchmark_only(self) -> None:
        status_code, payload = methodology()
        self.assertEqual(status_code, 200)
        self.assertFalse(payload["data"]["suitable_for_runtime_routing"])
        self.assertEqual(payload["data"]["freshness_tier"], "benchmark")

    def test_integration_guide_documents_public_endpoints_and_no_runtime_routing(self) -> None:
        guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")
        self.assertIn("GET /v0/dashboard-summary?window=1h", guide)
        self.assertIn('"suitable_for_runtime_routing": false', guide)
        self.assertIn("not live autonomous routing", guide)
        self.assertIn("refresh=1", guide)

    def test_data_guide_documents_external_inputs_and_decision_layers(self) -> None:
        guide = DATA_GUIDE.read_text(encoding="utf-8")
        self.assertIn("BigQuery", guide)
        self.assertIn("JSON export", guide)
        self.assertIn("Decision Layer Outputs", guide)
        self.assertIn("fetch_rows", guide)


if __name__ == "__main__":
    unittest.main()
