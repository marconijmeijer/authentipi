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


@router.get("/")
def dashboard(request: Request):
    with SessionLocal() as session:
        detections = session.execute(
            select(Detection).order_by(Detection.timestamp.desc()).limit(50)
        ).scalars().all()
        marks = session.execute(
            select(ImageMark).order_by(ImageMark.timestamp.desc()).limit(20)
        ).scalars().all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"detections": detections, "marks": marks, "stats": stats()},
    )


@router.get("/partials/detections")
def detections_partial(request: Request):
    with SessionLocal() as session:
        detections = session.execute(
            select(Detection).order_by(Detection.timestamp.desc()).limit(50)
        ).scalars().all()
    return templates.TemplateResponse(
        request, "_detections_table.html", {"detections": detections}
    )


@router.get("/partials/marks")
def marks_partial(request: Request):
    with SessionLocal() as session:
        marks = session.execute(
            select(ImageMark).order_by(ImageMark.timestamp.desc()).limit(20)
        ).scalars().all()
    return templates.TemplateResponse(request, "_marks_table.html", {"marks": marks})


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
