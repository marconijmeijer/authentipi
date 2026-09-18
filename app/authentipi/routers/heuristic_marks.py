from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter
from sqlalchemy import select

from ..db import SessionLocal
from ..models import HeuristicMark

router = APIRouter(prefix="/api/heuristic-marks")


class HeuristicMarkReport(BaseModel):
    url: str
    client_ip: str
    mime_type: str
    label: str
    score: float
    model_name: str


@router.post("")
def report_heuristic_mark(mark: HeuristicMarkReport):
    with SessionLocal() as session:
        session.add(
            HeuristicMark(
                url=mark.url,
                client_ip=mark.client_ip,
                mime_type=mark.mime_type,
                label=mark.label,
                score=mark.score,
                model_name=mark.model_name,
            )
        )
        session.commit()
    return {"status": "recorded"}


@router.get("/check")
def check_heuristic_marks(urls: str):
    wanted = [u for u in urls.split(",") if u]
    if not wanted:
        return []

    with SessionLocal() as session:
        rows = session.execute(
            select(HeuristicMark)
            .where(HeuristicMark.url.in_(wanted))
            .order_by(HeuristicMark.timestamp.desc())
        ).scalars().all()

    seen: set[str] = set()
    results = []
    for row in rows:
        if row.url in seen:
            continue
        seen.add(row.url)
        results.append(
            {
                "url": row.url,
                "label": row.label,
                "score": row.score,
                "model_name": row.model_name,
            }
        )
    return results


@router.get("")
def list_heuristic_marks(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with SessionLocal() as session:
        rows = session.execute(
            select(HeuristicMark)
            .order_by(HeuristicMark.timestamp.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() + "Z",
            "url": r.url,
            "client_ip": r.client_ip,
            "mime_type": r.mime_type,
            "label": r.label,
            "score": r.score,
            "model_name": r.model_name,
        }
        for r in rows
    ]
