import os
import pathlib
import unittest
import json


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestPhase0Harness(unittest.TestCase):
    def test_public_integration_guide_documents_adapter_architecture(self) -> None:
        guide = ROOT / "docs" / "data-and-decision-layer-integration.md"
        self.assertTrue(guide.exists(), f"missing public integration guide: {guide}")
        content = guide.read_text(encoding="utf-8")
        self.assertIn("Adapter Contract", content)

    def test_sample_fixture_exists(self) -> None:
        self.assertTrue((ROOT / "sample_data" / "solana_evidence_rows.json").exists())

    def test_agents_md_human_write_only_marker(self) -> None:
        agents = ROOT / "AGENTS.md"
        if not agents.exists():
            self.skipTest("AGENTS.md is human-managed and not present in this repo snapshot")
        content = agents.read_text(encoding="utf-8")
        self.assertRegex(content, r"(?i)human-write-only")

    def test_no_service_account_key_path(self) -> None:
        self.assertEqual(os.environ.get("SERVICE_ACCOUNT_KEY_PATH"), None)

    def test_health_client_module_has_no_bq_import(self) -> None:
        client = ROOT / "pipeline" / "adapter" / "upstream_health_client.py"
        self.assertTrue(client.exists(), "health client module should exist")
        content = client.read_text(encoding="utf-8")
        self.assertNotIn("bigquery", content.lower())

    def test_public_ci_runs_core_release_checks(self) -> None:
        workflow = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(workflow.exists(), "missing public CI workflow")
        content = workflow.read_text(encoding="utf-8")
        private_term_pattern = "|".join(
            [
                "Project " + "DG",
                "project_" + "dg",
                "canopy-" + "main",
                "canopy_" + "prod_us",
                "@canopy" + "systems.xyz",
                "Dev" + "an",
                "alan_" + "approved",
            ]
        )
        for expected in (
            "make doctor",
            "make lint-phase0",
            "python3 -m unittest discover -s tests/unit",
            "npm audit --audit-level=moderate",
            "npm run build",
            private_term_pattern,
        ):
            self.assertIn(expected, content)

    def test_dashboard_lockfile_is_tracked_release_artifact(self) -> None:
        self.assertTrue((ROOT / "dashboard" / "package-lock.json").exists())
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn("dashboard/package-lock.json", gitignore)
        package_json = json.loads((ROOT / "dashboard" / "package.json").read_text(encoding="utf-8"))
        self.assertRegex(package_json["dependencies"]["vite"], r"^\^6\.4\.[2-9]")
