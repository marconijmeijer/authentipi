"""AuthentiPi mitmproxy addon.

Two responsibilities:
- Inspect image responses for C2PA Content Credentials manifests, classify
  what they claim (source type, signer trust), and report matches to the
  AuthentiPi backend (/api/marks).
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
import urllib.request

import c2pa
import requests
from mitmproxy import http

logger = logging.getLogger("authentipi.proxy")

# Reachable by the proxy container itself (server-to-server reporting over
# the docker network) -- normally the internal service name, not localhost.
INTERNAL_APP_URL = os.environ.get("AUTHENTIPI_INTERNAL_APP_URL", "http://app:8080")

# Fase 3, experimental: the local AI-image classifier service. Optional --
# if unset or unreachable, this feature is simply skipped.
CLASSIFIER_URL = os.environ.get("AUTHENTIPI_CLASSIFIER_URL", "http://classifier:8082")

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

TRUST_ANCHORS_URL = "https://contentcredentials.org/trust/anchors.pem"

# https://cv.iptc.org/newscodes/digitalsourcetype/ -- the IPTC controlled
# vocabulary C2PA actions use for `digitalSourceType`. Dutch labels for the
# ones most relevant to "is this AI, an edit, or a capture".
SOURCE_TYPE_LABELS = {
    "trainedAlgorithmicMedia": "AI-gegenereerd",
    "compositeWithTrainedAlgorithmicMedia": "Deels AI-gegenereerd (samengesteld)",
    "algorithmicMedia": "Algoritmisch gegenereerd",
    "dataDrivenMedia": "Datagestuurd gegenereerd",
    "digitalArt": "Digitale kunst",
    "virtualRecording": "Virtuele opname (bv. render/game)",
    "digitalCapture": "Camera-opname",
    "negativeFilm": "Filmopname (negatief)",
    "positiveFilm": "Filmopname (positief)",
    "print": "Gescande afdruk",
    "minorHumanEdits": "Licht bewerkt",
    "compositeCapture": "Samengestelde opname",
}


def _build_context():
    """Load the official C2PA trust anchor list so manifest validation can
    tell a genuinely-issued signature apart from a self-signed one. Falls
    back to an unconfigured context (manifest presence/tamper checks still
    work, trust classification won't) if the fetch fails, e.g. offline."""
    try:
        with urllib.request.urlopen(TRUST_ANCHORS_URL, timeout=10) as resp:
            anchors = resp.read().decode("utf-8")
        settings = c2pa.Settings.from_dict(
            {"verify": {"verify_cert_anchors": True}, "trust": {"trust_anchors": anchors}}
        )
        logger.info("C2PA trust anchors geladen van %s", TRUST_ANCHORS_URL)
        return c2pa.Context(settings)
    except Exception:
        logger.exception(
            "kon C2PA trust anchors niet laden van %s -- vertrouwensstatus wordt niet bepaald",
            TRUST_ANCHORS_URL,
        )
        return c2pa.Context()


def _classify_source_type(manifest: dict) -> str | None:
    """Walk the c2pa.actions(.v2) assertion and return a Dutch label for the
    *last* action that carries a digitalSourceType -- i.e. the type that
    best represents the file's current/final state after any edits."""
    label = None
    for assertion in manifest.get("assertions", []):
        if "actions" not in assertion.get("label", ""):
            continue
        for action in assertion.get("data", {}).get("actions", []):
            source_type = action.get("digitalSourceType")
            if source_type:
                label = SOURCE_TYPE_LABELS.get(source_type.rstrip("/").rsplit("/", 1)[-1], label)
    return label


class AuthentiPiAddon:
    def __init__(self) -> None:
        self._context = _build_context()

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
        if self._inspect_c2pa(flow, mime_type):
            return  # a verified/self-signed manifest is authoritative
        self._inspect_heuristic(flow, mime_type)

    def _inspect_c2pa(self, flow: http.HTTPFlow, mime_type: str) -> bool:
        """Returns True if a (structurally valid) C2PA manifest was found
        and reported -- regardless of trust status."""
        try:
            reader = c2pa.Reader.try_create(
                mime_type, io.BytesIO(flow.response.content), context=self._context
            )
        except Exception:
            logger.exception("c2pa read mislukt voor %s", flow.request.pretty_url)
            return False

        if reader is None:
            return False

        try:
            manifest_json = json.loads(reader.json())
        except Exception:
            logger.exception("kon C2PA manifest niet parsen voor %s", flow.request.pretty_url)
            return False
        finally:
            reader.close()

        # "Invalid" means the manifest itself failed structural/tamper
        # checks (e.g. the file was modified after signing, or a required
        # field is malformed) -- don't present that as Content Credentials,
        # but also don't fall through to the heuristic check: a tampered
        # manifest is a stronger (if different) signal than "no signal".
        validation_state = manifest_json.get("validation_state")
        if validation_state == "Invalid":
            logger.warning(
                "C2PA manifest ongeldig voor %s, niet gerapporteerd", flow.request.pretty_url
            )
            return True

        active = manifest_json.get("active_manifest")
        manifest = manifest_json.get("manifests", {}).get(active, {}) if active else {}

        trusted: bool | None
        if validation_state == "Trusted":
            trusted = True
        elif validation_state == "Valid":
            trusted = False
        else:
            trusted = None

        try:
            requests.post(
                f"{INTERNAL_APP_URL}/api/marks",
                json={
                    "url": flow.request.pretty_url,
                    "client_ip": self._client_ip(flow),
                    "mime_type": mime_type,
                    "claim_generator": manifest.get("claim_generator"),
                    "summary": None,
                    "source_type": _classify_source_type(manifest),
                    "trusted": trusted,
                },
                timeout=3,
            )
        except requests.RequestException:
            logger.warning("kon C2PA-detectie niet rapporteren aan backend")
        return True

    def _inspect_heuristic(self, flow: http.HTTPFlow, mime_type: str) -> None:
        """Fase 3, experimental: no C2PA manifest was found, so ask the
        local classifier service for a statistical guess instead. Never
        raises -- the classifier is optional and this must never break the
        proxied response."""
        try:
            settings_resp = requests.get(f"{INTERNAL_APP_URL}/api/heuristic-settings", timeout=2)
            settings_resp.raise_for_status()
            settings = settings_resp.json()
        except requests.RequestException:
            return
        if not settings.get("enabled"):
            return

        try:
            classify_resp = requests.post(
                f"{CLASSIFIER_URL}/classify",
                data=flow.response.content,
                headers={"Content-Type": "application/octet-stream"},
                timeout=10,
            )
            classify_resp.raise_for_status()
            classify_result = classify_resp.json()
            predictions = classify_result.get("predictions", [])
        except requests.RequestException:
            logger.debug("classifier-service niet bereikbaar voor %s", flow.request.pretty_url)
            return

        artificial = next((p for p in predictions if p.get("label") == "artificial"), None)
        if artificial is None:
            return

        threshold = settings.get("threshold", 0.6)
        above_threshold = artificial.get("score", 0) >= threshold
        if not above_threshold and not settings.get("debug"):
            # Below threshold and debug mode off: nothing to show for this
            # one. With debug mode on, report it anyway (see module intro)
            # so scores are visible while tuning the threshold, not just
            # the ones that happened to clear it.
            return

        try:
            requests.post(
                f"{INTERNAL_APP_URL}/api/heuristic-marks",
                json={
                    "url": flow.request.pretty_url,
                    "client_ip": self._client_ip(flow),
                    "mime_type": mime_type,
                    "label": "artificial",
                    "score": artificial["score"],
                    "model_name": classify_result.get("model", "unknown"),
                    "above_threshold": above_threshold,
                },
                timeout=3,
            )
        except requests.RequestException:
            logger.warning("kon heuristische detectie niet rapporteren aan backend")

    def _inject_marker(self, flow: http.HTTPFlow) -> None:
        flow.response.headers.pop("Content-Security-Policy", None)
        flow.response.headers.pop("Content-Security-Policy-Report-Only", None)

        content = flow.response.content
        if b"</head>" in content:
            flow.response.content = content.replace(b"</head>", MARKER_SCRIPT_TAG + b"</head>", 1)
        elif b"</body>" in content:
            flow.response.content = content.replace(b"</body>", MARKER_SCRIPT_TAG + b"</body>", 1)


addons = [AuthentiPiAddon()]
