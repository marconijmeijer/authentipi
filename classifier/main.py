"""AuthentiPi experimental AI-image classifier service (Fase 3).

Unlike the C2PA check in the proxy service, this is NOT a cryptographic
verification of anything -- it's a statistical guess from a local ML model
about whether an image looks AI-generated. It has real, measured false
negatives (see README) and should never be presented with the same
confidence as a C2PA manifest check.

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
from PIL import Image
from transformers import pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("authentipi.classifier")

MODEL_NAME = os.environ.get("AUTHENTIPI_CLASSIFIER_MODEL", "umm-maybe/AI-image-detector")

_classifier = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _classifier
    logger.info("Model laden: %s (dit kan even duren bij de eerste start)...", MODEL_NAME)
    _classifier = pipeline("image-classification", model=MODEL_NAME)
    logger.info("Model geladen.")
    yield


app = FastAPI(title="AuthentiPi experimental classifier", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "ready": _classifier is not None}


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
