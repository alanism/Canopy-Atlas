import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "dashboard" / "src" / "App.jsx"
CSS = ROOT / "dashboard" / "src" / "styles.css"
PACKAGE = ROOT / "dashboard" / "package.json"


class TestPhase8Dashboard(unittest.TestCase):
    def test_dashboard_title_falls_back_when_x402_signal_unavailable(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn('FALLBACK_TITLE = "CANOPY ATLAS / EVIDENCE CONSOLE"', source)
        self.assertIn("FALLBACK_TITLE", source)

    def test_no_x402_claim_when_protocol_unknown(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn("x402 Fee & Route Transparency Dashboard", source)
        self.assertIn("Runtime routing disabled.", source)
        self.assertIn("runtime routing", source)

    def test_empty_data_state(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("Empty evidence field", source)
        self.assertIn("No cached route rows yet.", source)
        self.assertIn("No route-share data yet.", source)

    def test_long_tail_bucket_visible(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("long_tail_volume_pct", source)
        self.assertIn("Coverage and labeling incomplete.", source)

    def test_under_review_section_visible(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("UNDER REVIEW", source)
        self.assertIn("under_review_routes", source)

    def test_no_nan_or_undefined(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("Number.isNaN", source)
        self.assertIn('return "\\u2014";', source)

    def test_dashboard_uses_summary_endpoint(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn('SUMMARY_ENDPOINT = "/v0/dashboard-summary?window=1h"', source)
        self.assertIn("fetch(SUMMARY_ENDPOINT)", source)

    def test_dashboard_has_three_required_panels(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("ROUTE HEALTH × COST", source)
        self.assertIn("OBSERVED ROUTES", source)
        self.assertIn("ROUTE SHARE", source)

    def test_methodology_page_renders_and_api_cta_present(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("METHODOLOGY", source)
        self.assertIn("ARCHIVE SNAPSHOT", source)
        self.assertIn('/v0/dashboard-summary?window=1h"', source)

    def test_recharts_dependency_declared(self) -> None:
        package = PACKAGE.read_text(encoding="utf-8")
        self.assertIn('"recharts"', package)

    def test_responsive_mobile_styles_exist(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("grid-template-columns: 1fr", css)

    def test_atlas_console_copy_is_evidence_not_routing(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("Observed route evidence from the latest benchmark window.", source)
        self.assertIn("Cost, share, and settlement health for observed routes.", source)
        self.assertIn("Benchmark-grade evidence only.", source)
        self.assertIn("Capture the current dashboard state for audit or review.", source)

    def test_removed_storytelling_copy(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn("OpenClaw", source)
        self.assertNotIn("Agents do not need", source)
        self.assertNotIn("Payment buys access", source)
        self.assertNotIn("Not custody", source)
        self.assertNotIn("Not execution", source)


if __name__ == "__main__":
    unittest.main()
