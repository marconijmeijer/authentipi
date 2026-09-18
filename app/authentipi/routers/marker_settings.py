from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from ..db import SessionLocal
from ..models import MarkerSettings

router = APIRouter(prefix="/api/marker-settings")

DEFAULTS = {
    "icon": "✓",
    "text": "Content Credentials",
    "text_color": "#111111",
    "bg_color": "#ffd400",
}


class MarkerSettingsPayload(BaseModel):
    icon: str
    text: str
    text_color: str
    bg_color: str


def _as_dict(row: MarkerSettings | None) -> dict:
    if row is None:
        return dict(DEFAULTS)
    return {
        "icon": row.icon,
        "text": row.text,
        "text_color": row.text_color,
        "bg_color": row.bg_color,
    }


@router.get("")
def get_marker_settings():
    with SessionLocal() as session:
        row = session.get(MarkerSettings, 1)
        return _as_dict(row)


@router.post("")
def set_marker_settings(payload: MarkerSettingsPayload):
    with SessionLocal() as session:
        row = session.get(MarkerSettings, 1)
        if row is None:
            row = MarkerSettings(id=1)
            session.add(row)
        row.icon = payload.icon
        row.text = payload.text
        row.text_color = payload.text_color
        row.bg_color = payload.bg_color
        session.commit()
        return _as_dict(row)
