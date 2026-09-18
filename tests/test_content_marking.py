"""
Integration tests for the /api/marks contract shared by the mitmproxy addon
(proxy/authentipi_addon.py, which reports marks) and marker.js (which checks
them). These call the API directly rather than going through a live proxy +
image server, so they run fast and without extra infrastructure.

An end-to-end test that exercises the actual proxy (mitmdump on :8081) with
a real C2PA-signed test image is documented as a manual procedure in
README.md under "Content-marking testen", since it needs a CA-trusted
client and a real image fixture.
"""

import uuid

from helpers import check_marks, report_mark


def test_reported_mark_is_returned_by_check():
    url = f"http://example.test/{uuid.uuid4()}.jpg"
    report_mark(url, claim_generator="Test Generator")

    results = check_marks([url, "http://example.test/never-reported.jpg"])

    matched = next((r for r in results if r["url"] == url), None)
    assert matched is not None, "verwachtte de zojuist gerapporteerde mark terug te krijgen"
    assert matched["claim_generator"] == "Test Generator"

    urls = {r["url"] for r in results}
    assert "http://example.test/never-reported.jpg" not in urls


def test_check_with_no_matches_returns_empty_list():
    url = f"http://example.test/{uuid.uuid4()}-unmarked.jpg"
    assert check_marks([url]) == []
