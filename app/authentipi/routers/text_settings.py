from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from ..db import SessionLocal
from ..models import TextMarkerSettings

router = APIRouter(prefix="/api/text-settings")

DEFAULTS = {
    "icon": "✐",
    "text": "Mogelijk AI-tekst (experimenteel)",
    "text_color": "#3a1f4d",
    "bg_color": "#d9b8ff",
    "enabled": False,
    "threshold": 0.8,
    "debug": False,
}


class TextSettingsPayload(BaseModel):
    icon: str
    text: str
    text_color: str
    bg_color: str
    enabled: bool
    threshold: float
    debug: bool = False


def _as_dict(row: TextMarkerSettings | None) -> dict:
    if row is None:
        return dict(DEFAULTS)
    return {
        "icon": row.icon,
        "text": row.text,
        "text_color": row.text_color,
        "bg_color": row.bg_color,
        "enabled": row.enabled,
        "threshold": row.threshold,
        "debug": row.debug,
    }


@router.get("")
def get_text_settings():
    with SessionLocal() as session:
        return _as_dict(session.get(TextMarkerSettings, 1))


@router.post("")
def set_text_settings(payload: TextSettingsPayload):
    with SessionLocal() as session:
        row = session.get(TextMarkerSettings, 1)
        if row is None:
            row = TextMarkerSettings(id=1)
            session.add(row)
        row.icon = payload.icon
        row.text = payload.text
        row.text_color = payload.text_color
        row.bg_color = payload.bg_color
        row.enabled = payload.enabled
        row.threshold = max(0.0, min(payload.threshold, 1.0))
        row.debug = payload.debug
        session.commit()
        return _as_dict(row)
