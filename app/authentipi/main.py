from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import log_watcher
from .db import init_db
from .rules import ruleset
from .routers import (
    api,
    dashboard,
    heuristic_marks,
    heuristic_settings,
    marker_settings,
    marks,
    tls_settings,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tls_settings.seed_exceptions()
    ruleset.load()
    task = asyncio.create_task(log_watcher.run())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="AuthentiPi", lifespan=lifespan)

# marker.js runs on arbitrary third-party pages (any site a client visits),
# so it needs cross-origin access to report/check marks. Data exposed here
# is non-sensitive (domain/URL level detection info on a trusted home LAN).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"


@app.get("/static/marker.js")
def marker_js():
    # Registered before the StaticFiles mount below so it takes priority
    # for this exact path. marker.js changes often during development, and
    # a client browser silently serving a stale cached copy from an
    # earlier visit (rather than re-fetching it) was a real, confusing bug
    # -- fixes to this file appeared to "not work" because the browser
    # never actually loaded the new version. No-store makes that
    # impossible regardless of what any upstream proxy does.
    return FileResponse(
        static_dir / "marker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(api.router)
app.include_router(dashboard.router)
app.include_router(marks.router)
app.include_router(marker_settings.router)
app.include_router(heuristic_marks.router)
app.include_router(heuristic_settings.router)

app.include_router(tls_settings.router)
