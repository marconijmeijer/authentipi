"""Temporary diagnostic endpoint: marker.js posts a summary of what it saw
on a real page so we can see what's happening in an actual client browser
(no devtools access) via `docker compose logs app`. Not persisted to the
database on purpose -- purely ephemeral, remove once no longer needed."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("authentipi.client_debug")

router = APIRouter(prefix="/api/client-debug")


@router.post("")
async def client_debug(request: Request):
    payload = await request.json()
    logger.info("CLIENT-DEBUG %s", payload)
    return {"status": "logged"}
