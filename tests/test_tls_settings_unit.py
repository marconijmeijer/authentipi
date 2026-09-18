"""Isolated TLS policy tests; no running services or production database needed."""
import os
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.TemporaryDirectory()
os.environ['AUTHENTIPI_DB_PATH'] = str(Path(_tmp.name) / 'test.db')
os.environ['AUTHENTIPI_TLS_SEED'] = str(Path(_tmp.name) / 'seed.yaml')

from starlette.requests import Request
from sqlalchemy import select
from authentipi.db import Base, engine, init_db, SessionLocal
from authentipi.models import TLSGroup, TLSException, TLSFailure
from authentipi.routers import tls_settings as tls


def request(origin=None):
    return Request({'type': 'http', 'method': 'POST', 'path': '/settings/tls',
                    'scheme': 'http', 'server': ('testserver', 80), 'query_string': b'',
                    'headers': [(b'host', b'testserver')] + ([(b'origin', origin.encode())] if origin else [])})


class TLSTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine); init_db()
        Path(os.environ['AUTHENTIPI_TLS_SEED']).write_text("ignore_hosts:\n  - '^apps\\.mzstatic\\.com:443$'\n")
        tls.seed_exceptions()

    def test_seed_is_once_and_disabled_policy_stays_empty(self):
        tls.seed_exceptions()
        with SessionLocal() as s:
            groups = s.scalars(select(TLSGroup)).all()
            self.assertEqual(len(groups), 1)
            groups[0].enabled = False; s.commit()
        self.assertEqual(tls.proxy_config(), {'ignore_hosts': []})
        tls.seed_exceptions()
        self.assertEqual(tls.proxy_config(), {'ignore_hosts': []})

    def test_normalization_and_rejection(self):
        self.assertEqual(tls.parse_target('https://EXAMPLE.com:8443/', 443), ('example.com', 8443))
        self.assertEqual(tls.normalize_host('bücher.de'), 'xn--bcher-kva.de')
        for host in ['*.apple.com', 'example.com/path', 'https://example.com/private', '^.*$', 'https://u:p@example.com', 'https://example.com/?x=1']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                tls.parse_target(host, 443)

    def test_deleting_all_groups_does_not_reimport_seed(self):
        tls.group_delete(1, request())
        tls.seed_exceptions()
        self.assertEqual(tls.proxy_config(), {'ignore_hosts': []})
        with SessionLocal() as s:
            self.assertEqual(s.scalars(select(TLSGroup)).all(), [])

    def test_move_disable_delete_and_exact_matching(self):
        import re
        tls.group_save(request(), 'Bank', 0, 'on')
        with SessionLocal() as s:
            bank = s.scalar(select(TLSGroup).where(TLSGroup.name == 'Bank')).id
        tls.entry_save(request(), 'https://example.com/', bank, 443)
        patterns = tls.proxy_config()['ignore_hosts']
        self.assertTrue(any(re.search(p, 'example.com:443') for p in patterns))
        for bad in ['example.com.attacker.org:443', 'www.example.com:443', 'example.com:8443']:
            self.assertFalse(any(re.search(p, bad) for p in patterns))
        tls.entry_save(request(), 'example.com', 1, 443)
        with SessionLocal() as s:
            rows = s.scalars(select(TLSException).where(TLSException.host == 'example.com')).all()
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0].group_id, 1)
            eid = rows[0].id
        tls.entry_delete(eid, request())
        self.assertEqual(len(tls.proxy_config()['ignore_hosts']), 1)
        tls.group_delete(bank, request())

    def test_failure_aggregation_and_promotion(self):
        payload = tls.FailurePayload(host='EXAMPLE.com', port=443, side='client', message='certificate rejected', client_ip='127.0.0.1')
        tls.report_failure(payload); tls.report_failure(payload)
        with SessionLocal() as s:
            row = s.scalar(select(TLSFailure)); self.assertEqual(row.count, 2)
            self.assertEqual(row.host, 'example.com')
        tls.entry_save(request(), payload.host, 1, payload.port)
        self.assertEqual(len(tls.proxy_config()['ignore_hosts']), 2)
        self.assertEqual(tls.settings(request()).status_code, 200)

    def test_cross_origin_form_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            tls.group_save(request('https://other.example'), 'Bad', 0, 'on')
        self.assertEqual(error.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
