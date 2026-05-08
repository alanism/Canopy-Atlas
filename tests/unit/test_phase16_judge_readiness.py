import pathlib
import unittest

from api.auth import has_valid_bearer_token


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestPhase16JudgeReadiness(unittest.TestCase):
    def test_shared_bearer_auth_helper_accepts_only_exact_token(self) -> None:
        self.assertTrue(has_valid_bearer_token({"Authorization": "Bearer test-token"}, "test-token"))
        self.assertTrue(has_valid_bearer_token({"authorization": "Bearer test-token"}, "test-token"))
        self.assertFalse(has_valid_bearer_token({"Authorization": "Bearer wrong"}, "test-token"))
        self.assertFalse(has_valid_bearer_token({"Authorization": "Basic test-token"}, "test-token"))
        self.assertFalse(has_valid_bearer_token({"Authorization": "Bearer test-token"}, ""))

    def test_internal_surfaces_use_shared_auth_helper(self) -> None:
        for relative_path in ("api/server.py", "api/internal_api.py", "api/agent_proxy.py"):
            content = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("has_valid_bearer_token", content, relative_path)

    def test_operator_manual_documents_required_dependencies(self) -> None:
        manual = ROOT / "docs" / "operators-manual.md"
        self.assertTrue(manual.exists())
        content = manual.read_text(encoding="utf-8")
        for expected in (
            "AgentCash",
            "BigQuery",
            "Cloud Run",
            "Project-DG compatible paid upstream evidence service (Coming Soon)",
            "ATLAS_ORCHESTRATOR_TOKEN",
            "AGENTCASH_VERIFIER_TOKEN",
            "sample mode",
            "No real secrets belong in this repository",
        ):
            self.assertIn(expected, content)

    def test_premortem_and_scorecard_are_judge_facing(self) -> None:
        premortem = ROOT / "docs" / "deployment-premortem.md"
        scorecard = ROOT / "docs" / "hackathon-judge-scorecard.md"
        self.assertTrue(premortem.exists())
        self.assertTrue(scorecard.exists())
        self.assertIn("Rollback", premortem.read_text(encoding="utf-8"))
        scorecard_content = scorecard.read_text(encoding="utf-8")
        self.assertIn("82/100", scorecard_content)
        self.assertIn("Functionality", scorecard_content)
        self.assertIn("Open-source/composability", scorecard_content)


if __name__ == "__main__":
    unittest.main()
