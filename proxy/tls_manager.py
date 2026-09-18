"""Live exception refresh and non-blocking, bounded TLS diagnostics."""
import asyncio
import json
import logging
import os
from pathlib import Path

import requests
from mitmproxy import ctx

log = logging.getLogger('authentipi.tls')
BACKEND = os.environ.get('AUTHENTIPI_INTERNAL_APP_URL', 'http://app:8080')


class TLSManager:
    def __init__(self):
        self.events = asyncio.Queue(maxsize=200)
        self.tasks = []

    def running(self):
        self.cache = Path(ctx.options.confdir) / 'tls-exceptions-cache.json'
        try:
            self.apply(json.loads(self.cache.read_text()))
        except (OSError, ValueError, TypeError):
            pass  # Existing static Apple rules remain until backend is reachable.
        self.tasks = [asyncio.create_task(self.refresh()), asyncio.create_task(self.report())]

    def apply(self, patterns):
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            raise ValueError('Invalid TLS configuration')
        if list(ctx.options.ignore_hosts) != patterns:
            ctx.options.update(ignore_hosts=patterns)
            log.info('TLS exceptions updated: %s hosts', len(patterns))

    def fetch(self):
        response = requests.get(BACKEND + '/api/tls/config', timeout=3)
        response.raise_for_status()
        return response.json()['ignore_hosts']

    async def refresh(self):
        while True:
            try:
                patterns = await asyncio.to_thread(self.fetch)
                self.apply(patterns)
                serialized = json.dumps(patterns)
                if not self.cache.exists() or self.cache.read_text() != serialized:
                    tmp = self.cache.with_suffix('.tmp')
                    tmp.write_text(serialized); tmp.replace(self.cache)
            except Exception as e:
                log.warning('TLS config unavailable; keeping last rules: %s', e)
            await asyncio.sleep(3)

    async def report(self):
        while True:
            event = await self.events.get()
            try:
                response = await asyncio.to_thread(requests.post, BACKEND + '/api/tls/failures', json=event, timeout=3)
                response.raise_for_status()
            except requests.RequestException:
                log.warning('TLS diagnostic could not be delivered')
            finally:
                self.events.task_done()

    def failure(self, data, side):
        server, client = data.context.server, data.context.client
        address = server.address
        host = address[0] if address else server.sni or client.sni
        if not host:
            return
        peer = client.peername
        event = dict(host=host, port=address[1] if address else 443,
                     client_ip=str(peer[0]) if peer else 'unknown', side=side,
                     message=str(data.conn.error or 'TLS handshake failed')[:1000])
        try:
            self.events.put_nowait(event)
        except asyncio.QueueFull:
            log.warning('TLS diagnostic queue full; dropping event')

    def tls_failed_client(self, data):
        self.failure(data, 'client')

    def tls_failed_server(self, data):
        self.failure(data, 'server')

    def done(self):
        for task in self.tasks:
            task.cancel()


addons = [TLSManager()]
