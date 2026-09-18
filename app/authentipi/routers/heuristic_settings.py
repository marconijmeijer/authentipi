from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from ..db import SessionLocal
from ..models import HeuristicMarkerSettings

router = APIRouter(prefix="/api/heuristic-settings")

DEFAULTS = {
    "icon": "?",
    "text": "Mogelijk AI (experimenteel)",
    "text_color": "#3a2a00",
    "bg_color": "#ffb84d",
    "enabled": False,
    "threshold": 0.6,
}


class HeuristicSettingsPayload(BaseModel):
    icon: str
    text: str
    text_color: str
    bg_color: str
    enabled: bool
    threshold: float


def _as_dict(row: HeuristicMarkerSettings | None) -> dict:
    if row is None:
        return dict(DEFAULTS)
    return {
        "icon": row.icon,
        "text": row.text,
        "text_color": row.text_color,
        "bg_color": row.bg_color,
        "enabled": row.enabled,
        "threshold": row.threshold,
    }


@router.get("")
def get_heuristic_settings():
    with SessionLocal() as session:
        return _as_dict(session.get(HeuristicMarkerSettings, 1))


@router.post("")
def set_heuristic_settings(payload: HeuristicSettingsPayload):
    with SessionLocal() as session:
        row = session.get(HeuristicMarkerSettings, 1)
        if row is None:
            row = HeuristicMarkerSettings(id=1)
            session.add(row)
        row.icon = payload.icon
        row.text = payload.text
        row.text_color = payload.text_color
        row.bg_color = payload.bg_color
        row.enabled = payload.enabled
        row.threshold = max(0.0, min(payload.threshold, 1.0))
        session.commit()
        return _as_dict(row)
