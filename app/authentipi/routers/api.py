from __future__ import annotations

import datetime
from collections import Counter

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from .. import config
from ..db import SessionLocal
from ..models import CategoryState, Detection
from ..rules import ruleset

router = APIRouter(prefix="/api")


def _detection_dict(d: Detection) -> dict:
    return {
        "id": d.id,
        "timestamp": d.timestamp.isoformat() + "Z",
        "client_ip": d.client_ip,
        "domain": d.domain,
        "service": d.service,
        "category": d.category,
    }


@router.get("/detections")
def list_detections(limit: int = 100):
    limit = max(1, min(limit, 1000))
    with SessionLocal() as session:
        rows = session.execute(
            select(Detection).order_by(Detection.timestamp.desc()).limit(limit)
        ).scalars().all()
    return [_detection_dict(d) for d in rows]


@router.get("/stats")
def stats():
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    with SessionLocal() as session:
        rows = session.execute(
            select(Detection).where(Detection.timestamp >= since)
        ).scalars().all()

    by_category = Counter(d.category for d in rows)
    by_service = Counter(d.service for d in rows)
    by_client = Counter(d.client_ip for d in rows)

    return {
        "window_hours": 24,
        "total": len(rows),
        "by_category": dict(by_category),
        "by_service": dict(by_service.most_common(10)),
        "by_client": dict(by_client),
    }


@router.get("/rules")
def list_rules():
    return [
        {
            "domain": e.domain,
            "service": e.service,
            "category": e.category,
            "source_list": e.source_list,
        }
        for e in ruleset.all_entries()
    ]


@router.get("/categories")
def list_categories():
    with SessionLocal() as session:
        states = {s.category: s.enabled for s in session.execute(select(CategoryState)).scalars()}
    return [
        {"category": c, "enabled": states.get(c, True)} for c in config.KNOWN_CATEGORIES
    ]


@router.post("/categories/{category}")
def set_category(category: str, enabled: bool):
    if category not in config.KNOWN_CATEGORIES:
        raise HTTPException(status_code=404, detail="unknown category")
    with SessionLocal() as session:
        state = session.get(CategoryState, category)
        if state is None:
            state = CategoryState(category=category, enabled=enabled)
            session.add(state)
        else:
            state.enabled = enabled
        session.commit()
    return {"category": category, "enabled": enabled}
