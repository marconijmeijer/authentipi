from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import log_watcher
from .db import init_db
from .rules import ruleset
from .routers import api, dashboard

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

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(api.router)
app.include_router(dashboard.router)
