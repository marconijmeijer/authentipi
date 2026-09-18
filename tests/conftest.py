import pytest
import requests

from helpers import API_BASE, DNS_HOST


@pytest.fixture(scope="session", autouse=True)
def ensure_stack_running():
    try:
        resp = requests.get(f"{API_BASE}/api/categories", timeout=3)
        resp.raise_for_status()
    except requests.RequestException as exc:
        pytest.fail(
            f"AuthentiPi lijkt niet bereikbaar op {API_BASE} (dns host: {DNS_HOST}). "
            f"Start eerst de stack met 'docker compose up -d'. Fout: {exc}"
        )
