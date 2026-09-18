import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True
    )
    client_ip: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    service: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, index=True)


class CategoryState(Base):
    __tablename__ = "category_state"

    category: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class MarkerSettings(Base):
    """Singleton row (id=1) configuring how marker.js badges flagged
    content in the client's browser."""

    __tablename__ = "marker_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    icon: Mapped[str] = mapped_column(String, default="✓")
    text: Mapped[str] = mapped_column(String, default="Content Credentials")
    text_color: Mapped[str] = mapped_column(String, default="#111111")
    bg_color: Mapped[str] = mapped_column(String, default="#ffd400")


class ImageMark(Base):
    """A C2PA Content Credentials manifest found by the mitmproxy addon
    while inspecting an image/video response in transit."""

    __tablename__ = "image_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True
    )
    url: Mapped[str] = mapped_column(String, index=True)
    client_ip: Mapped[str] = mapped_column(String, index=True)
    mime_type: Mapped[str] = mapped_column(String)
    claim_generator: Mapped[str] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(String, nullable=True)
    # Human-readable classification derived from the manifest's c2pa.actions
    # digitalSourceType (e.g. "AI-gegenereerd", "Camera-opname"). Null when
    # the manifest carries no action assertions to classify.
    source_type: Mapped[str] = mapped_column(String, nullable=True)
    # True: signer chains to a trusted C2PA root (validation_state
    # "Trusted"). False: manifest is structurally valid but the signer is
    # not trusted (e.g. self-signed). Null: undetermined.
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=True)
