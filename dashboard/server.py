"""Static dashboard server with runtime API base injection."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def write_runtime_config() -> None:
    api_base_url = os.environ.get("CANOPY_DASHBOARD_API_BASE_URL", "")
    config_path = Path("/app/dist/config.js")
    config_path.write_text(f'window.CANOPY_API_BASE_URL = "{api_base_url}";\n', encoding="utf-8")


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/v0" or self.path.startswith("/v0/") or self.path in {
            "/openapi.json",
            "/llms.txt",
            "/agents.txt",
        }:
            self._proxy_api()
            return
        super().do_GET()

    def _proxy_api(self) -> None:
        api_base_url = os.environ.get("CANOPY_DASHBOARD_API_BASE_URL", "").rstrip("/")
        if not api_base_url:
            self.send_error(503, "CANOPY_DASHBOARD_API_BASE_URL is not configured")
            return
        headers = {"Accept": "application/json"}
        identity_token = _cloud_run_identity_token(api_base_url)
        if identity_token:
            headers["Authorization"] = f"Bearer {identity_token}"
        request = Request(f"{api_base_url}{self.path}", headers=headers)
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def _cloud_run_identity_token(audience: str) -> str | None:
    metadata_url = (
        "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity"
        f"?audience={quote(audience, safe='')}"
    )
    request = Request(metadata_url, headers={"Metadata-Flavor": "Google"})
    try:
        with urlopen(request, timeout=2) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def main() -> None:
    write_runtime_config()
    os.chdir("/app/dist")
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler).serve_forever()


if __name__ == "__main__":
    main()
