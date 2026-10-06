from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter
from sqlalchemy import select

from ..db import SessionLocal
from ..models import TextMark

router = APIRouter(prefix="/api/text-marks")


class TextMarkReport(BaseModel):
    url: str
    client_ip: str
    paragraph_index: int
    excerpt: str
    label: str
    score: float
    model_name: str
    above_threshold: bool = True


@router.post("")
def report_text_mark(mark: TextMarkReport):
    with SessionLocal() as session:
        session.add(
            TextMark(
                url=mark.url,
                client_ip=mark.client_ip,
                paragraph_index=mark.paragraph_index,
                excerpt=mark.excerpt[:160],
                label=mark.label,
                score=mark.score,
                model_name=mark.model_name,
                above_threshold=mark.above_threshold,
            )
        )
        session.commit()
    return {"status": "recorded"}


@router.get("")
def list_text_marks(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with SessionLocal() as session:
        rows = session.execute(
            select(TextMark).order_by(TextMark.timestamp.desc()).offset(offset).limit(limit)
        ).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() + "Z",
            "url": r.url,
            "client_ip": r.client_ip,
            "paragraph_index": r.paragraph_index,
            "excerpt": r.excerpt,
            "label": r.label,
            "score": r.score,
            "model_name": r.model_name,
            "above_threshold": r.above_threshold,
        }
        for r in rows
    ]
