from __future__ import annotations

import logging
import os

import requests
from pydantic import BaseModel
from fastapi import APIRouter, Request
from sqlalchemy import select

from ..db import SessionLocal
from ..models import TextMark, TextMarkerSettings
from .text_settings import _as_dict as text_settings_dict

logger = logging.getLogger("authentipi.text_marks")

# Reachable from the app container over the docker network. Separate from
# the proxy's own AUTHENTIPI_CLASSIFIER_URL env var (same default, set
# independently since these are two different containers).
CLASSIFIER_URL = os.environ.get("AUTHENTIPI_CLASSIFIER_URL", "http://classifier:8082")

router = APIRouter(prefix="/api/text-marks")


class TextMarkReport(BaseModel):
    url: str
    client_ip: str
    paragraph_index: int
    excerpt: str
    label: str
    score: float
    model_name: str
    above_threshold: bool = True


@router.post("")
def report_text_mark(mark: TextMarkReport):
    with SessionLocal() as session:
        session.add(
            TextMark(
                url=mark.url,
                client_ip=mark.client_ip,
                paragraph_index=mark.paragraph_index,
                excerpt=mark.excerpt[:160],
                label=mark.label,
                score=mark.score,
                model_name=mark.model_name,
                above_threshold=mark.above_threshold,
            )
        )
        session.commit()
    return {"status": "recorded"}


class ClassifyRequest(BaseModel):
    url: str
    texts: list[str]


@router.post("/classify")
def classify_and_mark(payload: ClassifyRequest, request: Request):
    """Called directly by marker.js (via the proxy's same-origin
    /__authentipi/ reverse-proxy) with paragraph text read straight from
    the live DOM -- i.e. after any client-side rendering/hydration has
    already happened. This replaced an earlier approach where the proxy
    addon extracted <p> tags from the raw HTML response: on sites that
    client-side re-render their article body from embedded JSON state
    (nu.nl included), that raw HTML never matched what the browser
    actually showed, so badges spliced into it were simply discarded when
    the page re-rendered. Reading textContent from the live DOM sidesteps
    that entirely, the same way marker.js already handles images that
    change after the initial page load.

    Trust note: unlike image marks (reported server-side by the addon,
    which already inspected the real response bytes), this endpoint takes
    the caller's word for both the page URL and the paragraph text, since
    it's invoked by page JavaScript running on whatever site the client
    visits. Acceptable for a self-hosted LAN tool; would need tightening
    for anything more adversarial.
    """
    with SessionLocal() as session:
        settings = text_settings_dict(session.get(TextMarkerSettings, 1))
    if not settings.get("enabled"):
        return {"results": []}

    texts = [t for t in payload.texts if t and t.strip()]
    if not texts:
        return {"results": []}

    try:
        resp = requests.post(
            f"{CLASSIFIER_URL}/classify-text", json={"texts": texts}, timeout=20
        )
        resp.raise_for_status()
        classify_result = resp.json()
    except requests.RequestException:
        logger.warning("tekst-classifier niet bereikbaar")
        return {"results": []}

    threshold = settings.get("threshold", 0.8)
    debug = settings.get("debug", False)
    model_name = classify_result.get("model", "unknown")
    client_ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else "unknown"
    )

    results = []
    with SessionLocal() as session:
        for index, (text, result) in enumerate(zip(texts, classify_result.get("results", []))):
            predictions = result.get("predictions", [])
            fake = next(
                (p for p in predictions if p.get("label", "").lower() == "fake"), None
            )
            if fake is None:
                continue
            score = fake.get("score", 0.0)
            above_threshold = score >= threshold
            if not above_threshold and not debug:
                continue

            session.add(
                TextMark(
                    url=payload.url,
                    client_ip=client_ip,
                    paragraph_index=index,
                    excerpt=text[:160],
                    label="Fake",
                    score=score,
                    model_name=model_name,
                    above_threshold=above_threshold,
                )
            )
            results.append({"index": index, "score": score, "above_threshold": above_threshold})
        session.commit()

    return {"model": model_name, "results": results}


@router.get("")
def list_text_marks(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with SessionLocal() as session:
        rows = session.execute(
            select(TextMark).order_by(TextMark.timestamp.desc()).offset(offset).limit(limit)
        ).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() + "Z",
            "url": r.url,
            "client_ip": r.client_ip,
            "paragraph_index": r.paragraph_index,
            "excerpt": r.excerpt,
            "label": r.label,
            "score": r.score,
            "model_name": r.model_name,
            "above_threshold": r.above_threshold,
        }
        for r in rows
    ]
