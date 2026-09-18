"""
Integration tests for Fase 3's experimental /api/heuristic-marks and
/api/heuristic-settings contracts, shared by the mitmproxy addon (which
reports marks when the local classifier crosses the threshold) and
marker.js (which checks them and renders the badge).

These call the API directly, not the actual classifier service (which is a
separate, heavy, opt-in docker-compose profile) -- so they verify the
contract, not the model's accuracy.
"""

import uuid

from helpers import (
    check_heuristic_marks,
    get_heuristic_settings,
    report_heuristic_mark,
    set_heuristic_settings,
)


def test_reported_heuristic_mark_is_returned_by_check():
    url = f"http://example.test/{uuid.uuid4()}.jpg"
    report_heuristic_mark(url, label="artificial", score=0.82, model_name="test-model")

    results = check_heuristic_marks([url, "http://example.test/never-reported.jpg"])

    matched = next((r for r in results if r["url"] == url), None)
    assert matched is not None
    assert matched["label"] == "artificial"
    assert matched["score"] == 0.82
    assert matched["model_name"] == "test-model"

    urls = {r["url"] for r in results}
    assert "http://example.test/never-reported.jpg" not in urls


def test_heuristic_settings_round_trip():
    original = get_heuristic_settings()
    try:
        updated = set_heuristic_settings(enabled=True, threshold=0.42, text="Test badge")
        assert updated["enabled"] is True
        assert updated["threshold"] == 0.42
        assert updated["text"] == "Test badge"

        assert get_heuristic_settings() == updated
    finally:
        set_heuristic_settings(**original)
