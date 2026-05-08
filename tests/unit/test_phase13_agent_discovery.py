import http.client
import json
import pathlib
import threading
import unittest
from http.server import ThreadingHTTPServer
from typing import Any

from api.discovery import endpoint_index, openapi_document
from api.server import CanopyHandler


ROOT = pathlib.Path(__file__).resolve().parents[2]
DASHBOARD_SERVER = ROOT / "dashboard" / "server.py"


class TestPhase13AgentDiscovery(unittest.TestCase):
    def test_openapi_has_required_agent_discovery_fields(self) -> None:
        document = openapi_document()
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertEqual(document["info"]["title"], "Canopy Atlas Benchmark API")
        self.assertIn("x-guidance", document["info"])
        self.assertEqual(document["info"]["x-preferred-paid-proxy"]["endpoint"], "POST /v1/route-policy")
        self.assertIn("/v0/dashboard-summary", document["paths"])
        self.assertIn("/v0", document["paths"])
        self.assertIn("DashboardSummaryEnvelope", document["components"]["schemas"])

    def test_openapi_documents_v0_without_payment_metadata(self) -> None:
        document = openapi_document()
        expected_paths = {
            "/v0",
            "/v0/dashboard-summary",
            "/v0/routes",
            "/v0/fees",
            "/v0/route-share",
            "/v0/reliability",
            "/v0/status",
            "/v0/methodology",
        }
        self.assertEqual(expected_paths, set(document["paths"]))
        self.assertFalse(_contains_key(document, "x-payment-info"))
        for path_item in document["paths"].values():
            operation = path_item["get"]
            self.assertNotIn("402", operation.get("responses", {}))

    def test_endpoint_index_lists_public_benchmark_surfaces(self) -> None:
        payload = endpoint_index()
        self.assertFalse(payload["meta"]["suitable_for_runtime_routing"])
        self.assertEqual(payload["meta"]["payment_status"], "not_payable")
        self.assertEqual(payload["meta"]["preferred_paid_proxy"]["price"]["amount"], "0.05")
        self.assertEqual(payload["data"]["paid_agent_proxy"]["status"], "paid_first_dual_mode")
        self.assertEqual(payload["data"]["supported_windows"], ["15m", "1h", "24h", "7d"])
        self.assertEqual(
            payload["data"]["solana_showcase"]["caip2"],
            "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        )
        paths = {endpoint["path"] for endpoint in payload["data"]["endpoints"]}
        self.assertIn("/v0/dashboard-summary", paths)
        self.assertIn("/v0/methodology", paths)

    def test_server_exposes_openapi_agents_text_and_index(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), CanopyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            openapi_status, openapi_headers, openapi_body = _get(server.server_port, "/openapi.json")
            self.assertEqual(openapi_status, 200)
            self.assertEqual(openapi_headers["content-type"], "application/json")
            self.assertEqual(json.loads(openapi_body)["openapi"], "3.1.0")

            index_status, _, index_body = _get(server.server_port, "/v0")
            self.assertEqual(index_status, 200)
            self.assertEqual(json.loads(index_body)["meta"]["payment_status"], "not_payable")
            self.assertEqual(json.loads(index_body)["meta"]["preferred_paid_proxy"]["endpoint"], "POST /v1/route-policy")

            llms_status, llms_headers, llms_body = _get(server.server_port, "/llms.txt")
            self.assertEqual(llms_status, 200)
            self.assertIn("text/markdown", llms_headers["content-type"])
            self.assertIn("POST /v1/route-policy", llms_body)
            self.assertIn("GET /v0/status", llms_body)
            self.assertIn("benchmark evidence only", llms_body)

            agents_status, _, agents_body = _get(server.server_port, "/agents.txt")
            self.assertEqual(agents_status, 200)
            self.assertEqual(agents_body, llms_body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_dashboard_proxy_forwards_agent_discovery_paths(self) -> None:
        source = DASHBOARD_SERVER.read_text(encoding="utf-8")
        self.assertIn('self.path == "/v0"', source)
        self.assertIn('"/openapi.json"', source)
        self.assertIn('"/llms.txt"', source)
        self.assertIn('"/agents.txt"', source)


def _get(port: int, path: str) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, headers, body
    finally:
        connection.close()


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


if __name__ == "__main__":
    unittest.main()
