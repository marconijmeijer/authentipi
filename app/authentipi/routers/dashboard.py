from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .. import config
from ..db import SessionLocal
from ..models import (
    CategoryState,
    Detection,
    HeuristicMark,
    HeuristicMarkerSettings,
    ImageMark,
    MarkerSettings,
)
from ..rules import ruleset
from .api import stats
from .heuristic_settings import _as_dict as heuristic_settings_dict
from .marker_settings import _as_dict as marker_settings_dict

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
        heuristic_marks, heuristic_has_more = _paginate(
            session, HeuristicMark, HeuristicMark.timestamp, 0, PAGE_SIZE
        )
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
            "heuristic_marks": heuristic_marks,
            "heuristic_offset": 0,
            "heuristic_limit": PAGE_SIZE,
            "heuristic_has_more": heuristic_has_more,
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


@router.get("/partials/heuristic-marks")
def heuristic_marks_partial(request: Request, offset: int = 0, limit: int = PAGE_SIZE):
    offset = max(0, offset)
    with SessionLocal() as session:
        heuristic_marks, has_more = _paginate(
            session, HeuristicMark, HeuristicMark.timestamp, offset, limit
        )
    return templates.TemplateResponse(
        request,
        "_heuristic_marks_table.html",
        {
            "heuristic_marks": heuristic_marks,
            "heuristic_offset": offset,
            "heuristic_limit": limit,
            "heuristic_has_more": has_more,
        },
    )


@router.get("/settings")
def settings_index():
    return RedirectResponse(url="/settings/categories", status_code=303)


@router.get("/settings/categories")
def settings_categories(request: Request):
    with SessionLocal() as session:
        states = {
            s.category: s.enabled for s in session.execute(select(CategoryState)).scalars()
        }
    categories = [
        {"category": c, "enabled": states.get(c, True)} for c in config.KNOWN_CATEGORIES
    ]
    return templates.TemplateResponse(
        request,
        "settings_categories.html",
        {"categories": categories, "active": "categories"},
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
    return RedirectResponse(url="/settings/categories", status_code=303)


@router.get("/settings/marker")
def settings_marker(request: Request):
    with SessionLocal() as session:
        marker = marker_settings_dict(session.get(MarkerSettings, 1))
    return templates.TemplateResponse(
        request, "settings_marker.html", {"marker": marker, "active": "marker"}
    )


@router.post("/settings/marker")
def update_marker_settings(
    request: Request,
    icon: str = Form(""),
    text: str = Form("Content Credentials"),
    text_color: str = Form("#111111"),
    bg_color: str = Form("#ffd400"),
):
    with SessionLocal() as session:
        row = session.get(MarkerSettings, 1)
        if row is None:
            row = MarkerSettings(id=1)
            session.add(row)
        row.icon = icon
        row.text = text
        row.text_color = text_color
        row.bg_color = bg_color
        session.commit()
    return RedirectResponse(url="/settings/marker", status_code=303)


@router.get("/settings/heuristic")
def settings_heuristic(request: Request):
    with SessionLocal() as session:
        heuristic = heuristic_settings_dict(session.get(HeuristicMarkerSettings, 1))
    return templates.TemplateResponse(
        request, "settings_heuristic.html", {"heuristic": heuristic, "active": "heuristic"}
    )


@router.post("/settings/heuristic")
def update_heuristic_settings(
    request: Request,
    icon: str = Form(""),
    text: str = Form("Mogelijk AI (experimenteel)"),
    text_color: str = Form("#3a2a00"),
    bg_color: str = Form("#ffb84d"),
    threshold: float = Form(0.6),
    enabled: str = Form(""),
    debug: str = Form(""),
):
    with SessionLocal() as session:
        row = session.get(HeuristicMarkerSettings, 1)
        if row is None:
            row = HeuristicMarkerSettings(id=1)
            session.add(row)
        row.icon = icon
        row.text = text
        row.text_color = text_color
        row.bg_color = bg_color
        row.threshold = max(0.0, min(threshold, 1.0))
        row.enabled = enabled == "on"
        row.debug = debug == "on"
        session.commit()
    return RedirectResponse(url="/settings/heuristic", status_code=303)


@router.get("/settings/rules")
def settings_rules(request: Request):
    return templates.TemplateResponse(
        request, "settings_rules.html", {"rules": ruleset.all_entries(), "active": "rules"}
    )
