from __future__ import annotations

import os
import time

import dns.resolver
import requests

DNS_HOST = os.environ.get("AUTHENTIPI_TEST_DNS_HOST", "127.0.0.1")
API_BASE = os.environ.get("AUTHENTIPI_TEST_API_BASE", "http://localhost:8080")


def dns_query(domain: str) -> None:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [DNS_HOST]
    resolver.timeout = 3
    resolver.lifetime = 3
    resolver.resolve(domain, "A")


def get_detections(limit: int = 50) -> list[dict]:
    resp = requests.get(f"{API_BASE}/api/detections", params={"limit": limit}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def latest_detection_id() -> int:
    detections = get_detections(limit=1)
    return detections[0]["id"] if detections else 0


def wait_for_new_detection(domain: str, since_id: int, timeout: float = 10.0) -> dict | None:
    """Poll the API until a detection for `domain` with id > since_id shows up,
    or the timeout expires (used to assert something was NOT detected)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for d in get_detections(limit=50):
            if d["domain"] == domain and d["id"] > since_id:
                return d
        time.sleep(0.5)
    return None


def set_category(category: str, enabled: bool) -> None:
    resp = requests.post(
        f"{API_BASE}/api/categories/{category}",
        params={"enabled": str(enabled).lower()},
        timeout=5,
    )
    resp.raise_for_status()


def get_category_enabled(category: str) -> bool:
    resp = requests.get(f"{API_BASE}/api/categories", timeout=5)
    resp.raise_for_status()
    for c in resp.json():
        if c["category"] == category:
            return bool(c["enabled"])
    raise KeyError(f"unknown category: {category}")
