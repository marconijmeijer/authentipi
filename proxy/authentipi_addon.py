"""AuthentiPi mitmproxy addon.

Two responsibilities:
- Inspect image responses for C2PA Content Credentials manifests and report
  matches to the AuthentiPi backend (/api/marks).
- Inject a small marker script into HTML responses so the client browser can
  badge any flagged images directly on the page (via marker.js, served by
  the backend, which queries /api/marks/check).

Note: injecting a script requires dropping any Content-Security-Policy on
the page, since a strict CSP would otherwise block it. That is an explicit
trade-off of the MITM approach.
"""

from __future__ import annotations

import io
import json
import logging
import os

import c2pa
import requests
from mitmproxy import http

logger = logging.getLogger("authentipi.proxy")

# Reachable by the proxy container itself (server-to-server reporting over
# the docker network) -- normally the internal service name, not localhost.
INTERNAL_APP_URL = os.environ.get("AUTHENTIPI_INTERNAL_APP_URL", "http://app:8080")

# Reachable by CLIENT BROWSERS on the LAN (used in the injected <script src>
# tag, and by marker.js itself for its own fetch() calls back to the API).
# Must be overridden to the host's LAN IP for real multi-device use.
PUBLIC_APP_URL = os.environ.get("AUTHENTIPI_APP_BASE_URL", "http://localhost:8080")
MARKER_SCRIPT_TAG = f'<script src="{PUBLIC_APP_URL}/static/marker.js"></script>'.encode()

IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/heic",
    "image/heif",
}


class AuthentiPiAddon:
    def response(self, flow: http.HTTPFlow) -> None:
        if flow.response is None or not flow.response.content:
            return

        content_type = (
            flow.response.headers.get("content-type", "").split(";")[0].strip().lower()
        )

        if content_type in IMAGE_MIME_TYPES:
            self._inspect_image(flow, content_type)
        elif content_type == "text/html":
            self._inject_marker(flow)

    def _client_ip(self, flow: http.HTTPFlow) -> str:
        address = flow.client_conn.address
        return address[0] if address else "unknown"

    def _inspect_image(self, flow: http.HTTPFlow, mime_type: str) -> None:
        try:
            reader = c2pa.Reader.try_create(mime_type, io.BytesIO(flow.response.content))
        except Exception:
            logger.exception("c2pa read mislukt voor %s", flow.request.pretty_url)
            return

        if reader is None:
            return

        claim_generator = None
        try:
            manifest_json = json.loads(reader.json())
            active = manifest_json.get("active_manifest")
            manifest = manifest_json.get("manifests", {}).get(active, {}) if active else {}
            claim_generator = manifest.get("claim_generator")
        except Exception:
            logger.exception("kon C2PA manifest niet parsen voor %s", flow.request.pretty_url)
        finally:
            reader.close()

        try:
            requests.post(
                f"{INTERNAL_APP_URL}/api/marks",
                json={
                    "url": flow.request.pretty_url,
                    "client_ip": self._client_ip(flow),
                    "mime_type": mime_type,
                    "claim_generator": claim_generator,
                    "summary": None,
                },
                timeout=3,
            )
        except requests.RequestException:
            logger.warning("kon C2PA-detectie niet rapporteren aan backend")

    def _inject_marker(self, flow: http.HTTPFlow) -> None:
        flow.response.headers.pop("Content-Security-Policy", None)
        flow.response.headers.pop("Content-Security-Policy-Report-Only", None)

        content = flow.response.content
        if b"</head>" in content:
            flow.response.content = content.replace(b"</head>", MARKER_SCRIPT_TAG + b"</head>", 1)
        elif b"</body>" in content:
            flow.response.content = content.replace(b"</body>", MARKER_SCRIPT_TAG + b"</body>", 1)


addons = [AuthentiPiAddon()]
