import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint
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


class HeuristicMarkerSettings(Base):
    """Singleton row (id=1) configuring the badge for Fase 3's experimental,
    non-cryptographic AI-image classifier -- kept as a separate style from
    MarkerSettings on purpose, so an unreliable statistical guess never
    looks visually identical to a verified C2PA claim."""

    __tablename__ = "heuristic_marker_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    icon: Mapped[str] = mapped_column(String, default="?")
    text: Mapped[str] = mapped_column(String, default="Mogelijk AI (experimenteel)")
    text_color: Mapped[str] = mapped_column(String, default="#3a2a00")
    bg_color: Mapped[str] = mapped_column(String, default="#ffb84d")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Only badge when the "artificial" score is at or above this (0-1).
    threshold: Mapped[float] = mapped_column(Float, default=0.6)
    # Debug mode: report EVERY classified image, even below threshold, so
    # you can see actual scores while tuning the threshold instead of
    # guessing blind. Meant to be temporary, not left on -- noisy by design.
    debug: Mapped[bool] = mapped_column(Boolean, default=False)


class HeuristicMark(Base):
    """A local ML model's guess that an image (with no C2PA manifest) looks
    AI-generated. Explicitly NOT a verified claim -- see
    HeuristicMarkerSettings and README "Fase 3"."""

    __tablename__ = "heuristic_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True
    )
    url: Mapped[str] = mapped_column(String, index=True)
    client_ip: Mapped[str] = mapped_column(String, index=True)
    mime_type: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String)
    # False for rows only reported because debug mode was on -- the score
    # didn't actually cross the configured threshold at report time.
    above_threshold: Mapped[bool] = mapped_column(Boolean, default=True)


class TLSMigration(Base):
    __tablename__ = 'tls_migration'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class TLSGroup(Base):
    __tablename__ = 'tls_groups'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TLSException(Base):
    __tablename__ = 'tls_exceptions'
    __table_args__ = (UniqueConstraint('host', 'port'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, index=True)
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer, default=443)


class TLSFailure(Base):
    __tablename__ = 'tls_failures'
    __table_args__ = (UniqueConstraint('host', 'port', 'side'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(1000))
    client_ip: Mapped[str] = mapped_column(String(64))
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
