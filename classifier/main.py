"""AuthentiPi experimental AI-content classifier service (Fase 3).

Unlike the C2PA check in the proxy service, this is NOT a cryptographic
verification of anything -- it's a statistical guess from a local ML model
about whether content looks AI-generated. It has real, measured false
negatives/positives (see README) and should never be presented with the
same confidence as a C2PA manifest check.

Two independent models/endpoints:
- /classify (image): see README "Fase 3".
- /classify-text (text, per paragraph/sentence): NOT a detector of any
  specific provider's watermark (e.g. OpenAI's "textGrain", announced Oct
  2026) -- that requires the provider's own secret key/detector and can't
  be replicated locally. This is a generic stylistic AI-text classifier,
  English-only, with the same (if not worse) reliability caveats as the
  image classifier. Treat it as a hint, not a finding.

Runs as its own service (rather than inside `app`) because the ML
dependencies (transformers + torch) are large and this is meant to be an
explicitly opt-in, heavier "Fase 3" component -- not something every
AuthentiPi install pays for by default.
"""

from __future__ import annotations

import io
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from PIL import Image
from transformers import pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("authentipi.classifier")

MODEL_NAME = os.environ.get("AUTHENTIPI_CLASSIFIER_MODEL", "umm-maybe/AI-image-detector")
TEXT_MODEL_NAME = os.environ.get(
    "AUTHENTIPI_TEXT_CLASSIFIER_MODEL", "openai-community/roberta-base-openai-detector"
)

_classifier = None
_text_classifier = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _classifier, _text_classifier
    logger.info("Model laden: %s (dit kan even duren bij de eerste start)...", MODEL_NAME)
    _classifier = pipeline("image-classification", model=MODEL_NAME)
    logger.info("Model laden: %s...", TEXT_MODEL_NAME)
    _text_classifier = pipeline(
        "text-classification", model=TEXT_MODEL_NAME, top_k=None, truncation=True
    )
    logger.info("Beide modellen geladen.")
    yield


app = FastAPI(title="AuthentiPi experimental classifier", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "text_model": TEXT_MODEL_NAME,
        "ready": _classifier is not None and _text_classifier is not None,
    }


@app.post("/classify")
async def classify(request: Request):
    if _classifier is None:
        raise HTTPException(status_code=503, detail="model nog aan het laden")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="lege request body")

    try:
        image = Image.open(io.BytesIO(body)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="kon afbeelding niet decoderen")

    results = _classifier(image)
    # transformers returns a list of {"label": ..., "score": ...}, sorted
    # by score descending.
    return {"model": MODEL_NAME, "predictions": results}


class ClassifyTextRequest(BaseModel):
    texts: list[str]


@app.post("/classify-text")
async def classify_text(payload: ClassifyTextRequest):
    if _text_classifier is None:
        raise HTTPException(status_code=503, detail="model nog aan het laden")

    texts = [t for t in payload.texts if t and t.strip()]
    if not texts:
        return {"model": TEXT_MODEL_NAME, "results": []}

    raw = _text_classifier(texts)
    # top_k=None gives, per input text, a list of {"label", "score"} for
    # every class. Returned as-is (like /classify for images) so the
    # caller can look up a specific label's score directly -- needed for
    # debug mode, which wants the "how AI-like" score even on paragraphs
    # where it isn't the top prediction.
    return {
        "model": TEXT_MODEL_NAME,
        "results": [{"predictions": predictions} for predictions in raw],
    }
