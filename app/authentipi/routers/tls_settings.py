"""Grouped TLS exceptions and bounded, aggregated handshake diagnostics."""
import datetime as dt
import ipaddress
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..db import SessionLocal
from ..models import TLSGroup, TLSException, TLSFailure, TLSMigration
from .dashboard import templates

router = APIRouter()


def normalize_host(value: str) -> str:
    value = value.strip().lower().rstrip('.')
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        value = value.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError('Vul een geldige hostnaam in.')
    if len(value) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x) for x in value.split('.')):
        raise ValueError('Gebruik een exacte hostnaam, zonder URL-pad, wildcard of regex.')
    return value


def parse_target(value: str, port: int) -> tuple[str, int]:
    if '://' in value:
        url = urlsplit(value.strip())
        if url.scheme != 'https' or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            raise ValueError('Gebruik een hostnaam of HTTPS-URL zonder pad, query of inloggegevens.')
        value, port = url.hostname or '', url.port or port
    if not 1 <= port <= 65535:
        raise ValueError('Poort moet tussen 1 en 65535 liggen.')
    return normalize_host(value), port


def check_origin(request: Request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Ongeldige herkomst van formulier.')


def seed_exceptions():
    """Import the existing exact-host config once, even if all groups are later deleted."""
    with SessionLocal() as s:
        if s.get(TLSMigration, 1):
            return
        if s.scalar(select(TLSGroup.id).limit(1)) is not None:
            s.add(TLSMigration(id=1)); s.commit()
            return
        path = Path(os.environ.get('AUTHENTIPI_TLS_SEED', '/tls-seed.yaml'))
        if not path.exists():
            return
        patterns = (yaml.safe_load(path.read_text()) or {}).get('ignore_hosts', [])
        group = TLSGroup(name='Apple')
        s.add(group); s.flush()
        for pattern in patterns:
            match = re.fullmatch(r'\^(.+):(\d+)\$', pattern)
            if not match:
                raise ValueError('TLS seed bevat een niet-exacte hostregel')
            host = normalize_host(match[1].replace('\\.', '.'))
            s.add(TLSException(group_id=group.id, host=host, port=int(match[2])))
        s.add(TLSMigration(id=1))
        s.commit()


def page(request, error=None, saved=False):
    with SessionLocal() as s:
        groups = s.scalars(select(TLSGroup).order_by(TLSGroup.name)).all()
        entries = s.scalars(select(TLSException).order_by(TLSException.host)).all()
        failures = s.scalars(select(TLSFailure).order_by(TLSFailure.last_seen.desc()).limit(100)).all()
        assigned = {(e.host, e.port): e.group_id for e in entries}
        return templates.TemplateResponse(request, 'settings_tls.html', dict(
            active='tls', groups=groups, entries=entries, failures=failures,
            assigned=assigned, error=error, saved=saved,
        ), status_code=400 if error else 200)


@router.get('/settings/tls')
def settings(request: Request, saved: bool = False):
    return page(request, saved=saved)


@router.post('/settings/tls/groups')
def group_save(request: Request, name: str = Form(...), group_id: int = Form(0), enabled: str = Form('')):
    check_origin(request)
    name = name.strip()
    if not name or len(name) > 60:
        return page(request, 'Geef de groep een naam van maximaal 60 tekens.')
    with SessionLocal() as s:
        duplicate = s.scalar(select(TLSGroup).where(TLSGroup.name == name, TLSGroup.id != group_id))
        if duplicate:
            return page(request, 'Deze groepsnaam bestaat al.')
        group = s.get(TLSGroup, group_id) if group_id else TLSGroup()
        if group is None:
            raise HTTPException(404)
        group.name, group.enabled = name, enabled == 'on'
        s.add(group); s.commit()
    return RedirectResponse('/settings/tls?saved=true', 303)


@router.post('/settings/tls/entries')
def entry_save(request: Request, host: str = Form(...), group_id: int = Form(...), port: int = Form(443)):
    check_origin(request)
    try:
        host, port = parse_target(host, port)
    except ValueError as e:
        return page(request, str(e))
    with SessionLocal() as s:
        if s.get(TLSGroup, group_id) is None:
            return page(request, 'Kies een bestaande groep.')
        entry = s.scalar(select(TLSException).where(TLSException.host == host, TLSException.port == port))
        if entry is None:
            entry = TLSException(host=host, port=port)
        entry.group_id = group_id
        s.add(entry); s.commit()
    return RedirectResponse('/settings/tls?saved=true', 303)


@router.post('/settings/tls/entries/{entry_id}/delete')
def entry_delete(entry_id: int, request: Request):
    check_origin(request)
    with SessionLocal() as s:
        s.execute(delete(TLSException).where(TLSException.id == entry_id)); s.commit()
    return RedirectResponse('/settings/tls?saved=true', 303)


@router.post('/settings/tls/groups/{group_id}/delete')
def group_delete(group_id: int, request: Request):
    check_origin(request)
    with SessionLocal() as s:
        s.execute(delete(TLSException).where(TLSException.group_id == group_id))
        s.execute(delete(TLSGroup).where(TLSGroup.id == group_id)); s.commit()
    return RedirectResponse('/settings/tls?saved=true', 303)


@router.get('/api/tls/config')
def proxy_config():
    with SessionLocal() as s:
        entries = s.scalars(select(TLSException).join(TLSGroup, TLSException.group_id == TLSGroup.id).where(TLSGroup.enabled.is_(True))).all()
        return {'ignore_hosts': sorted(f'^{re.escape(e.host)}:{e.port}$' for e in entries)}


class FailurePayload(BaseModel):
    host: str = Field(max_length=253)
    port: int = Field(ge=1, le=65535)
    side: str = Field(pattern='^(client|server)$')
    message: str = Field(max_length=1000)
    client_ip: str = Field(max_length=64)


@router.post('/api/tls/failures')
def report_failure(payload: FailurePayload):
    try:
        host = normalize_host(payload.host)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with SessionLocal() as s:
        row = s.scalar(select(TLSFailure).where(TLSFailure.host == host, TLSFailure.port == payload.port, TLSFailure.side == payload.side))
        if row is None:
            row = TLSFailure(host=host, port=payload.port, side=payload.side, count=0)
        row.count += 1
        row.message, row.client_ip = payload.message, payload.client_ip
        row.last_seen = dt.datetime.utcnow()
        s.add(row); s.flush()
        stale = select(TLSFailure.id).order_by(TLSFailure.last_seen.desc()).offset(500)
        s.execute(delete(TLSFailure).where(TLSFailure.id.in_(stale)))
        s.commit()
    return {'ok': True}
