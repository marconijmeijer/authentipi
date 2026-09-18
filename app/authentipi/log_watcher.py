from __future__ import annotations

import asyncio
import logging
import re

from . import config
from .db import SessionLocal
from .models import CategoryState, Detection
from .rules import ruleset

logger = logging.getLogger("authentipi.log_watcher")

# Matches dnsmasq's "query[A] example.com from 192.168.1.50" log lines.
QUERY_LINE = re.compile(r"query\[\w+\] (\S+) from (\S+)")


def _category_enabled(category: str) -> bool:
    with SessionLocal() as session:
        state = session.get(CategoryState, category)
        return state.enabled if state is not None else True


def _record_detection(domain: str, client_ip: str) -> None:
    entry = ruleset.match(domain)
    if entry is None:
        return
    if not _category_enabled(entry.category):
        return

    with SessionLocal() as session:
        session.add(
            Detection(
                client_ip=client_ip,
                domain=entry.domain,
                service=entry.service,
                category=entry.category,
            )
        )
        session.commit()
    logger.info("Detected %s (%s) requested by %s", entry.domain, entry.service, client_ip)


async def _tail(path) -> None:
    while not path.exists():
        logger.info("Waiting for dns log file at %s ...", path)
        await asyncio.sleep(2)

    with path.open("r") as f:
        f.seek(0, 2)  # start at end of file, only react to new queries
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue

            match = QUERY_LINE.search(line)
            if not match:
                continue

            domain, client_ip = match.group(1), match.group(2)
            _record_detection(domain, client_ip)


async def run() -> None:
    """Background task: tails the dnsmasq query log and records detections."""
    try:
        await _tail(config.DNS_LOG_PATH)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("log watcher crashed")
