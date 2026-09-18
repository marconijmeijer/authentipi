from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter
from sqlalchemy import select

from ..db import SessionLocal
from ..models import ImageMark

router = APIRouter(prefix="/api/marks")


class MarkReport(BaseModel):
    url: str
    client_ip: str
    mime_type: str
    claim_generator: str | None = None
    summary: str | None = None


@router.post("")
def report_mark(mark: MarkReport):
    with SessionLocal() as session:
        session.add(
            ImageMark(
                url=mark.url,
                client_ip=mark.client_ip,
                mime_type=mark.mime_type,
                claim_generator=mark.claim_generator,
                summary=mark.summary,
            )
        )
        session.commit()
    return {"status": "recorded"}


@router.get("/check")
def check_marks(urls: str):
    """Given a comma-separated list of URLs, return which ones have a known
    C2PA mark. Used by the in-page marker script."""
    wanted = [u for u in urls.split(",") if u]
    if not wanted:
        return []

    with SessionLocal() as session:
        rows = session.execute(
            select(ImageMark)
            .where(ImageMark.url.in_(wanted))
            .order_by(ImageMark.timestamp.desc())
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
                "claim_generator": row.claim_generator,
                "summary": row.summary,
            }
        )
    return results


@router.get("")
def list_marks(limit: int = 50):
    limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        rows = session.execute(
            select(ImageMark).order_by(ImageMark.timestamp.desc()).limit(limit)
        ).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() + "Z",
            "url": r.url,
            "client_ip": r.client_ip,
            "mime_type": r.mime_type,
            "claim_generator": r.claim_generator,
            "summary": r.summary,
        }
        for r in rows
    ]
