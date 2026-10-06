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

import html
import io
import json
import logging
import os
import re
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

# Any request whose path starts with this is served directly by the addon
# itself (reverse-proxied to the app backend) instead of being forwarded to
# whatever real site the client thinks it's talking to. Using a relative,
# same-origin path -- rather than an absolute http://<lan-ip>:8080 URL --
# means marker.js and its API calls always inherit the current page's own
# scheme and host. That matters concretely: an HTTPS page loading an
# http:// script or fetch()ing an http:// URL is "mixed content", which
# browsers block outright and silently (no visible error on the page,
# console-only) -- which is exactly why badges never appeared on any real
# HTTPS site before this. Since this proxy is already MITM-ing the TLS
# connection for whatever domain the client is visiting, it can terminate
# these same-origin requests directly, over that domain's own HTTPS,
# without needing a certificate of its own or a fixed LAN-IP setting.
PROXY_PATH_PREFIX = "/__authentipi"
MARKER_SCRIPT_TAG = f'<script src="{PROXY_PATH_PREFIX}/static/marker.js"></script>'.encode()

# Some sites deliver CSP via a <meta> tag instead of (or in addition to) a
# response header -- stripping only the header misses those and the
# injected marker script gets blocked anyway.
CSP_META_TAG_RE = re.compile(
    rb'<meta[^>]+http-equiv=["\']Content-Security-Policy(?:-Report-Only)?["\'][^>]*>',
    re.IGNORECASE,
)

IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/heic",
    "image/heif",
}

# Best-effort <p>...</p> extraction for Fase 3 text classification -- a
# real HTML parser would handle malformed/unclosed tags better, but this
# regex is cheap and good enough for well-formed pages (see README
# "Bekende beperkingen").
PARAGRAPH_RE = re.compile(rb"<p\b[^>]*>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(rb"<[^>]+>")
MIN_PARAGRAPH_CHARS = 60

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

    def request(self, flow: http.HTTPFlow) -> None:
        if flow.request.path.startswith(PROXY_PATH_PREFIX):
            self._serve_from_app(flow)
            return

        # Without this, a browser that already has an image cached from
        # before AuthentiPi was set up may serve it locally or via a
        # conditional GET (304 Not Modified, empty body) forever -- the
        # proxy then never sees real image bytes to inspect, and nothing
        # ever gets marked, silently. Stripping these forces a full
        # response every time so inspection can actually happen.
        flow.request.headers.pop("If-None-Match", None)
        flow.request.headers.pop("If-Modified-Since", None)

    def _serve_from_app(self, flow: http.HTTPFlow) -> None:
        """Reverse-proxy anything under PROXY_PATH_PREFIX to the app
        backend, and short-circuit -- the client's request never reaches
        whatever real site it nominally targeted. This is what makes
        marker.js and its API calls same-origin (and thus HTTPS, matching
        whatever page they're loaded from) without AuthentiPi needing its
        own trusted certificate."""
        sub_path = flow.request.path[len(PROXY_PATH_PREFIX):] or "/"
        # Third-party pages may only reach the read-only marker endpoints.
        allowed = {"/static/marker.js", "/api/marks/check", "/api/marker-settings",
                   "/api/heuristic-marks/check", "/api/heuristic-settings"}
        if flow.request.method != "GET" or sub_path.split("?", 1)[0] not in allowed:
            flow.response = http.Response.make(404, b"Not found")
            return
        target = f"{INTERNAL_APP_URL}{sub_path}"
        try:
            upstream = requests.request(
                method=flow.request.method,
                url=target,
                data=flow.request.content,
                headers={
                    k: v
                    for k, v in flow.request.headers.items()
                    if k.lower() not in ("host", "content-length")
                },
                timeout=10,
            )
        except requests.RequestException:
            logger.warning("AuthentiPi backend onbereikbaar voor %s", target)
            flow.response = http.Response.make(
                502, b"AuthentiPi backend unreachable", {"Content-Type": "text/plain"}
            )
            return

        headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        }
        headers["Cache-Control"] = "no-store"
        flow.response = http.Response.make(upstream.status_code, upstream.content, headers)

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.response is None or not flow.response.content:
            return

        content_type = (
            flow.response.headers.get("content-type", "").split(";")[0].strip().lower()
        )

        if content_type in IMAGE_MIME_TYPES:
            self._strip_cache_headers(flow)
            self._inspect_image(flow, content_type)
        elif content_type == "text/html":
            self._inject_marker(flow)

    def _strip_cache_headers(self, flow: http.HTTPFlow) -> None:
        """Stop the browser from caching this image response, so a later
        visit results in a real network request (and thus another chance
        for AuthentiPi to inspect it) instead of a silent local cache hit."""
        for header in ("Cache-Control", "Expires", "ETag", "Last-Modified", "Age"):
            flow.response.headers.pop(header, None)
        flow.response.headers["Cache-Control"] = "no-store"

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

        content = CSP_META_TAG_RE.sub(b"", flow.response.content)
        content = self._mark_text(flow, content)
        if b"</head>" in content:
            content = content.replace(b"</head>", MARKER_SCRIPT_TAG + b"</head>", 1)
        elif b"</body>" in content:
            content = content.replace(b"</body>", MARKER_SCRIPT_TAG + b"</body>", 1)
        flow.response.content = content

    def _mark_text(self, flow: http.HTTPFlow, content: bytes) -> bytes:
        """Fase 3, experimental: classify each <p> paragraph on the page
        and highlight the ones that look AI-written directly in the HTML.
        Unlike images (fetched as their own resource, checked client-side
        by marker.js after the fact), the addon already has the full page
        text here, synchronously, before it's sent to the browser -- so
        this marks the HTML directly instead of needing a separate
        check-and-badge round trip."""
        try:
            settings_resp = requests.get(f"{INTERNAL_APP_URL}/api/text-settings", timeout=2)
            settings_resp.raise_for_status()
            settings = settings_resp.json()
        except requests.RequestException:
            return content
        if not settings.get("enabled"):
            return content

        matches = list(PARAGRAPH_RE.finditer(content))
        candidates = []
        for match in matches:
            plain = TAG_RE.sub(b" ", match.group(1))
            try:
                plain_text = html.unescape(" ".join(plain.decode("utf-8", "ignore").split()))
            except Exception:
                continue
            if len(plain_text) >= MIN_PARAGRAPH_CHARS:
                candidates.append((match, plain_text))

        if not candidates:
            return content

        try:
            classify_resp = requests.post(
                f"{CLASSIFIER_URL}/classify-text",
                json={"texts": [text for _, text in candidates]},
                timeout=15,
            )
            classify_resp.raise_for_status()
            classify_result = classify_resp.json()
            results = classify_result.get("results", [])
        except requests.RequestException:
            logger.debug("text-classifier niet bereikbaar voor %s", flow.request.pretty_url)
            return content

        if len(results) != len(candidates):
            return content

        threshold = settings.get("threshold", 0.8)
        debug = settings.get("debug", False)
        model_name = classify_result.get("model", "unknown")

        # Process from the last match backward so earlier (lower-index,
        # not-yet-processed) match spans stay valid as this splices the
        # growing byte string -- matches never overlap in the original
        # content, so edits at/after a later match never shift an earlier
        # one's start/end.
        ordered = sorted(
            zip(candidates, results), key=lambda item: item[0][0].start(), reverse=True
        )
        for (match, plain_text), result in ordered:
            predictions = result.get("predictions", [])
            fake = next((p for p in predictions if p.get("label", "").lower() == "fake"), None)
            if fake is None:
                continue
            score = fake.get("score", 0.0)
            above_threshold = score >= threshold
            if not above_threshold and not debug:
                continue

            index = matches.index(match)
            content = self._splice_text_badge(content, match, score, above_threshold, settings)
            self._report_text_mark(flow, index, plain_text, "Fake", score, model_name, above_threshold)

        return content

    def _splice_text_badge(
        self,
        content: bytes,
        match: re.Match,
        score: float,
        above_threshold: bool,
        settings: dict,
    ) -> bytes:
        pct = round(score * 100)
        if above_threshold:
            icon = settings.get("icon", "✐")
            label_text = settings.get("text", "Mogelijk AI-tekst (experimenteel)")
            badge_label = f"{icon} {label_text} · {pct}%"
            style = f"background:{settings.get('bg_color', '#d9b8ff')};color:{settings.get('text_color', '#3a1f4d')};"
        else:
            badge_label = f"\U0001F41E debug: {pct}% (onder drempel)"
            style = "background:rgba(120,120,120,0.85);color:#fff;border:1px dashed #fff;"

        badge_html = (
            '<div style="position:absolute;top:-11px;right:8px;z-index:2147483647;'
            "font:600 11px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;"
            "padding:2px 6px;border-radius:999px;pointer-events:none;"
            f'box-shadow:0 1px 3px rgba(0,0,0,0.4);{style}">'
            f"{html.escape(badge_label)}</div>"
        ).encode("utf-8")
        wrapped = (
            b'<div style="position:relative;margin-top:14px;">'
            + match.group(0)
            + badge_html
            + b"</div>"
        )
        return content[: match.start()] + wrapped + content[match.end() :]

    def _report_text_mark(
        self,
        flow: http.HTTPFlow,
        paragraph_index: int,
        excerpt: str,
        label: str,
        score: float,
        model_name: str,
        above_threshold: bool,
    ) -> None:
        try:
            requests.post(
                f"{INTERNAL_APP_URL}/api/text-marks",
                json={
                    "url": flow.request.pretty_url,
                    "client_ip": self._client_ip(flow),
                    "paragraph_index": paragraph_index,
                    "excerpt": excerpt[:160],
                    "label": label,
                    "score": score,
                    "model_name": model_name,
                    "above_threshold": above_threshold,
                },
                timeout=3,
            )
        except requests.RequestException:
            logger.warning("kon tekst-detectie niet rapporteren aan backend")


addons = [AuthentiPiAddon()]
