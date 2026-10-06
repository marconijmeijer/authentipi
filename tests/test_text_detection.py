"""
Integration tests for Fase 3's experimental /api/text-marks and
/api/text-settings contracts. Classification itself happens client-side in
marker.js (reading live, post-hydration paragraph text and posting it to
/api/text-marks/classify), so these test the reporting and settings
contract directly -- not the client-side scanning logic, which is
exercised manually via proxy/test-fixtures/text-marking-test.html (see
README "Experimentele tekst-herkenning testen").
"""

import uuid

from helpers import (
    classify_text,
    get_text_settings,
    list_text_marks,
    report_text_mark,
    set_text_settings,
)


def test_reported_text_mark_appears_in_list():
    url = f"http://example.test/{uuid.uuid4()}-article"
    report_text_mark(
        url, paragraph_index=3, excerpt="A suspiciously formal paragraph.", score=0.91
    )

    marks = list_text_marks(limit=5)
    matched = next((m for m in marks if m["url"] == url), None)
    assert matched is not None
    assert matched["paragraph_index"] == 3
    assert matched["score"] == 0.91
    assert matched["above_threshold"] is True


def test_text_settings_round_trip():
    original = get_text_settings()
    try:
        updated = set_text_settings(enabled=True, threshold=0.55, debug=True)
        assert updated["enabled"] is True
        assert updated["threshold"] == 0.55
        assert updated["debug"] is True
        assert get_text_settings() == updated
    finally:
        set_text_settings(**original)


def test_classify_respects_disabled_setting():
    """/api/text-marks/classify is called by marker.js with live, post-hydration
    paragraph text -- this only tests the settings-gating contract (not the
    live classifier call itself, which is an optional service, same as the
    heuristic image classifier tests)."""
    original = get_text_settings()
    try:
        set_text_settings(enabled=False)
        result = classify_text(
            f"http://example.test/{uuid.uuid4()}-disabled", ["Any paragraph text here."]
        )
        assert result == {"results": []}
    finally:
        set_text_settings(**original)
