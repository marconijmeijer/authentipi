from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .. import config
from ..db import SessionLocal
from ..models import CategoryState, Detection, ImageMark
from ..rules import ruleset
from .api import stats

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAGE_SIZE = 10


def _paginate(session, model, order_col, offset: int, limit: int):
    """Fetch one extra row beyond `limit` to cheaply know whether a next
    page exists, without a separate COUNT query."""
    rows = session.execute(
        select(model).order_by(order_col.desc()).offset(offset).limit(limit + 1)
    ).scalars().all()
    has_more = len(rows) > limit
    return rows[:limit], has_more


@router.get("/")
def dashboard(request: Request):
    with SessionLocal() as session:
        detections, detections_has_more = _paginate(
            session, Detection, Detection.timestamp, 0, PAGE_SIZE
        )
        marks, marks_has_more = _paginate(session, ImageMark, ImageMark.timestamp, 0, PAGE_SIZE)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "detections": detections,
            "detections_offset": 0,
            "detections_limit": PAGE_SIZE,
            "detections_has_more": detections_has_more,
            "marks": marks,
            "marks_offset": 0,
            "marks_limit": PAGE_SIZE,
            "marks_has_more": marks_has_more,
            "stats": stats(),
        },
    )


@router.get("/partials/detections")
def detections_partial(request: Request, offset: int = 0, limit: int = PAGE_SIZE):
    offset = max(0, offset)
    with SessionLocal() as session:
        detections, has_more = _paginate(session, Detection, Detection.timestamp, offset, limit)
    return templates.TemplateResponse(
        request,
        "_detections_table.html",
        {
            "detections": detections,
            "detections_offset": offset,
            "detections_limit": limit,
            "detections_has_more": has_more,
        },
    )


@router.get("/partials/marks")
def marks_partial(request: Request, offset: int = 0, limit: int = PAGE_SIZE):
    offset = max(0, offset)
    with SessionLocal() as session:
        marks, has_more = _paginate(session, ImageMark, ImageMark.timestamp, offset, limit)
    return templates.TemplateResponse(
        request,
        "_marks_table.html",
        {
            "marks": marks,
            "marks_offset": offset,
            "marks_limit": limit,
            "marks_has_more": has_more,
        },
    )


@router.get("/settings")
def settings(request: Request):
    with SessionLocal() as session:
        states = {
            s.category: s.enabled for s in session.execute(select(CategoryState)).scalars()
        }
    categories = [
        {"category": c, "enabled": states.get(c, True)} for c in config.KNOWN_CATEGORIES
    ]
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"categories": categories, "rules": ruleset.all_entries()},
    )


@router.post("/settings/categories")
def update_categories(request: Request, enabled_categories: list[str] = Form(default=[])):
    with SessionLocal() as session:
        for category in config.KNOWN_CATEGORIES:
            state = session.get(CategoryState, category)
            is_enabled = category in enabled_categories
            if state is None:
                session.add(CategoryState(category=category, enabled=is_enabled))
            else:
                state.enabled = is_enabled
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)
