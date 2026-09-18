from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import log_watcher
from .db import init_db
from .rules import ruleset
from .routers import api, dashboard, marker_settings, marks

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(api.router)
app.include_router(dashboard.router)
app.include_router(marks.router)
app.include_router(marker_settings.router)
